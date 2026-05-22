"""
Tests for the LLM Service
==========================
Uses unittest.mock to patch AsyncOpenAI so no real API calls are made.

We test:
    - Successful chat completion and PR review
    - Empty response handling
    - Timeout, auth, connection, and rate-limit errors
    - Settings defaults are loaded when no args are provided
    - API key is never exposed in repr or error messages
"""
from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.services.llm_service import (
    LlmAuthError,
    LlmRateLimitError,
    LlmService,
    LlmServiceError,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_openai() -> Mock:
    """
    Mock the entire AsyncOpenAI class so no network calls happen.

    Returns the mock *instance* so callers can configure
    ``mock.chat.completions.create.return_value``.
    """
    mock_instance = AsyncMock()
    mock_instance.chat.completions.create = AsyncMock()

    patcher = patch("app.services.llm_service.AsyncOpenAI", return_value=mock_instance)
    patcher.start()

    yield mock_instance

    patcher.stop()


def _mock_completion(content: str | None) -> Mock:
    """Build a mocked chat completion response."""
    choice = Mock()
    choice.message = Mock()
    choice.message.content = content
    completion = Mock()
    completion.choices = [choice]
    return completion


# ── Successful requests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_chat_completion_returns_text(mock_openai: Mock):
    """A valid response should return the content as-is."""
    mock_openai.chat.completions.create.return_value = _mock_completion(
        "Hello **world**!"
    )

    svc = LlmService(api_key="sk-test", base_url="https://test.com/v1", model="test-model")
    result = await svc.generate_chat_completion(
        [{"role": "user", "content": "Say hello"}]
    )

    assert result == "Hello **world**!"


@pytest.mark.asyncio
async def test_generate_pr_review_returns_markdown(mock_openai: Mock):
    """generate_pr_review should wrap the prompt and return markdown."""
    mock_openai.chat.completions.create.return_value = _mock_completion(
        "## Review\n\nLooks good!"
    )

    svc = LlmService(api_key="sk-test", base_url="https://test.com/v1", model="test-model")
    result = await svc.generate_pr_review("Review this diff: ...")

    assert "## Review" in result
    assert "Looks good!" in result


@pytest.mark.asyncio
async def test_generate_chat_completion_passes_messages(mock_openai: Mock):
    """The messages list should be forwarded verbatim to the SDK."""
    mock_openai.chat.completions.create.return_value = _mock_completion("ok")

    messages = [
        {"role": "system", "content": "You are a reviewer"},
        {"role": "user", "content": "diff content"},
    ]

    svc = LlmService(api_key="sk-test", base_url="https://test.com/v1", model="test-model")
    await svc.generate_chat_completion(messages)

    mock_openai.chat.completions.create.assert_called_once()
    call_kwargs = mock_openai.chat.completions.create.call_args.kwargs
    assert call_kwargs["messages"] == messages


# ── Empty / None response ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_response_raises_error(mock_openai: Mock):
    """When the LLM returns empty content, an error should be raised."""
    mock_openai.chat.completions.create.return_value = _mock_completion("")

    svc = LlmService(api_key="sk-test", base_url="https://test.com/v1", model="test-model")

    with pytest.raises(LlmServiceError, match="empty"):
        await svc.generate_chat_completion([{"role": "user", "content": "hello"}])


@pytest.mark.asyncio
async def test_none_response_raises_error(mock_openai: Mock):
    """When the LLM returns None content, an error should be raised."""
    mock_openai.chat.completions.create.return_value = _mock_completion(None)

    svc = LlmService(api_key="sk-test", base_url="https://test.com/v1", model="test-model")

    with pytest.raises(LlmServiceError, match="empty"):
        await svc.generate_chat_completion([{"role": "user", "content": "hello"}])


# ── API errors ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_timeout_error(mock_openai: Mock):
    """APITimeoutError should be wrapped in a friendly message."""
    from openai import APITimeoutError

    mock_openai.chat.completions.create.side_effect = APITimeoutError("timed out")

    svc = LlmService(api_key="sk-test", base_url="https://test.com/v1", model="test-model")

    with pytest.raises(LlmServiceError, match="timed out"):
        await svc.generate_chat_completion([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_connection_error(mock_openai: Mock):
    """APIConnectionError should be wrapped."""
    from openai import APIConnectionError
    from httpx import Request

    mock_openai.chat.completions.create.side_effect = APIConnectionError(
        message="Connection refused", request=Request("GET", "https://test.com")
    )

    svc = LlmService(api_key="sk-test", base_url="https://test.com/v1", model="test-model")

    with pytest.raises(LlmServiceError, match="connect"):
        await svc.generate_chat_completion([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_auth_error(mock_openai: Mock):
    """AuthenticationError should raise LlmAuthError."""
    from openai import AuthenticationError as OAIError

    mock_openai.chat.completions.create.side_effect = OAIError(
        "Incorrect API key", response=Mock(), body=None
    )

    svc = LlmService(api_key="sk-test", base_url="https://test.com/v1", model="test-model")

    with pytest.raises(LlmAuthError, match="OPENCODE_API_KEY"):
        await svc.generate_chat_completion([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_rate_limit_error(mock_openai: Mock):
    """RateLimitError should raise LlmRateLimitError."""
    from openai import RateLimitError as OAIError

    mock_openai.chat.completions.create.side_effect = OAIError(
        "Rate limit hit", response=Mock(), body=None
    )

    svc = LlmService(api_key="sk-test", base_url="https://test.com/v1", model="test-model")

    with pytest.raises(LlmRateLimitError, match="rate limit"):
        await svc.generate_chat_completion([{"role": "user", "content": "hi"}])


# ── Settings integration ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_loads_defaults_from_settings(mock_openai: Mock):
    """
    When no arguments are passed, LlmService should load from app settings.
    """
    from pydantic import SecretStr

    mock_settings = AsyncMock()
    mock_settings.OPENCODE_API_KEY = SecretStr("sk-from-settings")
    mock_settings.OPENCODE_BASE_URL = "https://opencode.ai/zen/go/v1"
    mock_settings.OPENCODE_MODEL = "deepseek-v4-flash"

    with patch("app.services.llm_service.get_settings", return_value=mock_settings):
        svc = LlmService()

    mock_openai.chat.completions.create.return_value = _mock_completion("ok")
    result = await svc.generate_chat_completion([{"role": "user", "content": "hi"}])

    assert result == "ok"
    # Verify the SDK was called with the settings values
    call_kwargs = mock_openai.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "deepseek-v4-flash"


# ── Repr safety ───────────────────────────────────────────────────────────────


def test_repr_does_not_expose_key():
    """The repr() of LlmService should not contain the API key."""
    svc = LlmService(api_key="my-secret-key", base_url="https://test.com/v1", model="test-model")
    representation = repr(svc)

    assert "my-secret-key" not in representation
    assert "test-model" in representation
