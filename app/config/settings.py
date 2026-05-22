"""
Pydantic Settings — Typed Environment Variables
================================================
All configuration lives in one place so you can see every available setting
at a glance. Add new variables here as the project grows.

Key concepts:
    - Field(alias=...)     → maps the Python attribute name to the env var name
    - Field(default=...)   → provides a fallback if the env var is missing
    - SecretStr            → masks the value in __repr__ (prevents accidental leaks)
    - field_validator      → custom validation logic with beginner-friendly errors
    - model_config         → tells pydantic-settings where to look for values
"""

import os

from dotenv import load_dotenv
from pydantic import Field, SecretStr, field_validator
from pydantic_core import ValidationError  # specific exception for clean catching
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application-wide settings loaded from environment variables (and .env).

    All values are validated at startup — if a required variable is missing or
    invalid, pydantic raises a clear error with a helpful message before any
    business logic runs.
    """

    # ── GitHub ──────────────────────────────────────────────────────────────
    # Personal Access Token used to authenticate with the GitHub REST API.
    # SecretStr ensures the value is masked in logs (shows '********').
    GITHUB_TOKEN: SecretStr = Field(
        ...,
        description="GitHub Personal Access Token with repo scope",
    )

    # ── LLM Provider (OpenCode Go / OpenAI-compatible) ──────────────────────
    # API key for the OpenAI-compatible chat completions endpoint.
    OPENCODE_API_KEY: SecretStr = Field(
        ...,
        description="API key for OpenCode Go (or any OpenAI-compatible provider)",
    )

    # Base URL for the chat completions API.
    # Default: https://opencode.ai/zen/go/v1
    OPENCODE_BASE_URL: str = Field(
        default="https://opencode.ai/zen/go/v1",
        description="Base URL for the OpenAI-compatible API",
    )

    # Model identifier to use for code review.
    # Change this to switch between different models.
    OPENCODE_MODEL: str = Field(
        default="deepseek-v4-flash",
        description="Model name for chat completions",
    )

    # ── Review Limits ────────────────────────────────────────────────────────
    # Protect against PRs with hundreds of files or massive diffs.
    # These prevent the LLM from being overwhelmed (and you from being charged too much).
    MAX_FILES_TO_REVIEW: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of files to include in a single review",
    )

    MAX_PATCH_CHARS: int = Field(
        default=12000,
        ge=500,
        le=100_000,
        description="Maximum characters of diff/patch to send to the LLM",
    )

    # ──────────────────────────────────────────────────────────────────────────
    # Custom Validators — run AFTER pydantic checks that a value was provided,
    # but BEFORE the value is stored.  These give us a chance to reject empty
    # strings or malformed URLs with an error message beginners can act on.
    # ──────────────────────────────────────────────────────────────────────────

    @field_validator("GITHUB_TOKEN", "OPENCODE_API_KEY", mode="before")
    @classmethod
    def reject_empty_token(cls, v: object, info) -> object:
        """
        Reject tokens that are missing or set to an empty string.

        'mode="before"' means this runs BEFORE pydantic wraps the value in
        SecretStr, so we see the raw string from the environment.
        """
        raw = v
        # If the env var exists but is blank (GITHUB_TOKEN=), raw is "".
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            raise ValueError(
                f"{info.field_name} is required but was not found or is empty.\n"
                f"  → Set it in your .env file:\n"
                f"       {info.field_name}=your_value_here\n"
                f"  → Or export it in your shell:\n"
                f"       export {info.field_name}=your_value_here"
            )
        return raw

    @field_validator("OPENCODE_BASE_URL", mode="before")
    @classmethod
    def validate_base_url(cls, v: object) -> str:
        """Ensure the base URL looks like a valid HTTP(S) URL."""
        from urllib.parse import urlparse

        raw = v
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("OPENCODE_BASE_URL must be a non-empty string")

        parsed = urlparse(raw.strip())
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(
                f"OPENCODE_BASE_URL must be a valid URL (e.g. "
                f"https://opencode.ai/zen/go/v1), got: '{raw}'"
            )
        return raw.strip()

    @field_validator("OPENCODE_MODEL", mode="before")
    @classmethod
    def reject_empty_model(cls, v: object) -> str:
        """Reject an empty or blank model name."""
        if not isinstance(v, str) or not v.strip():
            raise ValueError("OPENCODE_MODEL must be a non-empty string")
        return v.strip()

    # ── Pydantic-Settings Configuration ──────────────────────────────────────
    #   env_file=".env"      → automatically load from .env file
    #   env_file_encoding    → assume UTF-8
    #   case_sensitive=False → GITHUB_TOKEN and github_token both work
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Module-level singleton — Settings is stateless, so we create it once and
# reuse it.  This avoids re-parsing .env on every import.
# ──────────────────────────────────────────────────────────────────────────────
_settings: Settings | None = None


def get_settings() -> Settings:
    """
    Return the cached Settings instance (creating it on first call).

    This is the recommended way to access settings throughout the app.
    Usage:  settings = get_settings()

    What happens on the first call:
        1. load_dotenv() reads .env into os.environ (if it exists)
        2. pydantic-settings reads all env vars and validates them
        3. If validation fails, a user-friendly error message is printed
           before the program exits.
    """
    global _settings

    if _settings is None:
        # ── Load .env file into the environment ─────────────────────────────
        # python-dotenv looks for .env in the current directory and parent
        # directories.  This makes env vars available to os.getenv() AND to
        # pydantic-settings, which reads from os.environ by default.
        load_dotenv()

        try:
            _settings = Settings()
        except ValidationError as exc:
            # ── Build a beginner-friendly error summary ─────────────────────
            lines = [
                "\n" + "=" * 60,
                "  ❌  Configuration Error",
                "=" * 60,
                "",
                "  One or more required environment variables are missing or",
                "  invalid.  Fix them and try again.\n",
            ]

            # Each error from pydantic is a dict like:
            #   {"loc": ("GITHUB_TOKEN",), "msg": "...", "type": "..."}
            for error in exc.errors():
                field_path = ".".join(str(p) for p in error["loc"])
                lines.append(f"    • {field_path}: {error['msg']}")

            lines.extend([
                "",
                "  ─── How to fix ───",
                f"    1. Open a terminal in {os.getcwd()}",
                "    2. Copy the example file:",
                "         cp .env.example .env",
                "    3. Edit .env and fill in the missing values",
                "    4. Re-run your command",
                "",
                "=" * 60,
                "",
            ])

            raise SystemExit("\n".join(lines)) from exc

    return _settings
