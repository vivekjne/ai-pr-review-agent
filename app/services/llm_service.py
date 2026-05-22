"""
LLM Service — OpenCode Go (OpenAI-Compatible API)
==================================================
Wraps the OpenAI Python SDK configured to talk to OpenCode Go's API.

OpenCode Go provides an OpenAI-compatible chat completions endpoint,
so we use the standard ``openai`` library with a custom ``base_url``.

Usage:
    svc = LlmService()
    review = await svc.generate_pr_review("Review this diff: ...")

Environment:
    Requires OPENCODE_API_KEY and OPENCODE_MODEL.
"""

from typing import Any

from openai import (
    APIError,
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError as OpenAIAuthError,
    RateLimitError as OpenAIRateLimitError,
)

from app.config.settings import get_settings


# ── Custom Exceptions ─────────────────────────────────────────────────────────


class LlmServiceError(Exception):
    """Base exception for all LLM service errors."""


class LlmAuthError(LlmServiceError):
    """Raised when the API key is invalid or missing."""


class LlmRateLimitError(LlmServiceError):
    """Raised when the API rate limit is hit."""


# ── Service Class ─────────────────────────────────────────────────────────────


class LlmService:
    """
    Client for calling the LLM to review pull request code.

    Uses the OpenAI Python SDK under the hood but points it at
    the OpenCode Go API endpoint for chat completions.

    Args:
        api_key:  OpenCode API key.  If None, loaded from settings.
        base_url: API base URL.  If None, loaded from settings.
        model:    Model name.  If None, loaded from settings.
    """

    # Default system message used when no override is provided.
    # The prompt builder sends detailed instructions as the user message;
    # this system message sets the overall persona.
    SYSTEM_MESSAGE: str = (
        "You are an expert senior software engineer reviewing a pull request. "
        "You produce structured, actionable Markdown reviews. "
        "Follow the output format and rules in the user's instructions exactly."
    )

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        # Load defaults from app settings if not explicitly provided.
        if api_key is not None and base_url is not None and model is not None:
            resolved_key = api_key
            resolved_base = base_url
            resolved_model = model
        else:
            settings = get_settings()
            resolved_key = api_key or settings.OPENCODE_API_KEY.get_secret_value()
            resolved_base = base_url or settings.OPENCODE_BASE_URL
            resolved_model = model or settings.OPENCODE_MODEL

        self._model = resolved_model
        self._base_url_stored = resolved_base

        self._client = AsyncOpenAI(
            api_key=resolved_key,
            base_url=resolved_base,
            timeout=120.0,  # LLM can be slow for large diffs
        )

    # ── Public API ──────────────────────────────────────────────────────────

    async def generate_chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
    ) -> str:
        """
        Send a list of chat messages and return the model's response text.

        Args:
            messages:   List of {"role": ..., "content": ...} dicts.
            temperature: Sampling temperature (0.0 = deterministic).

        Returns:
            The response text (always a non-empty string).

        Raises:
            LlmAuthError:       API key invalid / missing.
            LlmRateLimitError:  Rate limit exceeded.
            LlmServiceError:    Timeout, connection failure, empty response.
        """
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
            )
        except APITimeoutError:
            raise LlmServiceError(
                "LLM request timed out after 120s.\n"
                "  → Check your network connection or try a smaller diff."
            )
        except APIConnectionError:
            raise LlmServiceError(
                "Failed to connect to the LLM API.\n"
                f"  → Check OPENCODE_BASE_URL ({self._base_url(masked=True)}) "
                "is correct and reachable."
            )
        except OpenAIAuthError:
            raise LlmAuthError(
                "LLM authentication failed.\n"
                "  → Check that OPENCODE_API_KEY is valid and not expired.\n"
                "  → Get a key at: https://opencode.ai"
            )
        except OpenAIRateLimitError as exc:
            raise LlmRateLimitError(
                "LLM rate limit exceeded.\n"
                f"  → Try again later. Details: {exc}"
            )
        except APIError as exc:
            raise LlmServiceError(
                f"LLM API returned an error: {exc}"
            )

        content: str | None = response.choices[0].message.content

        if not content:
            raise LlmServiceError(
                "LLM returned an empty response.\n"
                "  → Try re-running the review."
            )

        return content

    async def generate_pr_review(self, user_prompt: str) -> str:
        """
        High-level method: sends a user prompt to the LLM with a fixed
        system message, and returns the generated review.

        The system message sets the reviewer persona.  The user prompt
        (built by :func:`prompt_builder.build_pr_review_prompt`) contains
        the PR context, output format instructions, rules, and diffs.

        Args:
            user_prompt: The full prompt built by the prompt builder.

        Returns:
            Markdown-formatted code review text.
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self.SYSTEM_MESSAGE},
            {"role": "user", "content": user_prompt},
        ]
        return await self.generate_chat_completion(messages)

    # ── Internal helpers ───────────────────────────────────────────────────

    def _base_url(self, masked: bool = False) -> str:
        """Return the base URL, optionally masked (scheme + host only)."""
        from urllib.parse import urlparse

        url = urlparse(self._base_url_stored)
        if masked:
            return f"{url.scheme}://{url.netloc}/..."
        return self._base_url_stored

    def __repr__(self) -> str:
        """Safe repr — never exposes the API key."""
        return f"LlmService(model={self._model!r})"
