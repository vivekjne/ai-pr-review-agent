"""
Configuration Module
====================
Manages application settings from environment variables and .env files.

Why pydantic-settings?
    - Automatically reads from environment variables
    - Validates types at startup (catches missing config early)
    - Supports .env files via python-dotenv
    - Provides typed, IDE-friendly access (autocomplete works!)

Usage:
    from app.config.settings import get_settings, Settings

    # Option A — cached convenience accessor (recommended)
    settings = get_settings()
    print(settings.OPENCODE_MODEL)  # → "deepseek-v4-flash"

    # Option B — direct instantiation for testing
    settings = Settings(_env_file=".env.test", ...)
"""

from app.config.review_config import load_review_config, ReviewConfig  # noqa: F401
from app.config.settings import get_settings, Settings  # noqa: F401
