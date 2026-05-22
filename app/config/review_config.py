"""
Review Configuration — .ai-review.yml
======================================
Loads repository-level configuration from a YAML file in the project root.

Config fields override hardcoded defaults, but are overridden by
environment variables and CLI flags:

    CLI flags  >  env vars  >  config file  >  hardcoded defaults

Usage:
    from app.config.review_config import load_review_config

    config = load_review_config()          # searches for .ai-review.yml
    if config:
        mode = config.mode                 # "full" | "quick" | "security"
        ignore_list = config.ignore        # additional glob skip patterns
        focus_list = config.focus          # review focus areas
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ── Default search path for config file ───────────────────────────────────────
CONFIG_FILENAMES: list[str] = [".ai-review.yml", ".ai-review.yaml"]


# ── Pydantic model ────────────────────────────────────────────────────────────


class ReviewConfig(BaseModel):
    """
    Repository-level config loaded from ``.ai-review.yml``.

    All fields have sensible defaults so the file is entirely optional.
    """

    multi_agent: bool = Field(
        default=False,
        description="Use multi-agent review (runs 5 specialist agents + 1 final synthesizer)",
    )
    mode: str = Field(
        default="full",
        description="Review mode: full, quick, security, performance, tests, architecture",
    )
    fail_on_high_risk: bool = Field(
        default=False,
        description="Exit with non-zero code if high-risk findings exist",
    )
    fail_on_request_changes: bool = Field(
        default=False,
        description="Exit with non-zero code if AI recommends Request Changes",
    )
    max_files: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum files to review (overrides MAX_FILES_TO_REVIEW)",
    )
    max_patch_chars: int = Field(
        default=12000,
        ge=500,
        le=100_000,
        description="Max diff chars (overrides MAX_PATCH_CHARS)",
    )
    ignore: list[str] = Field(
        default_factory=list,
        description="Glob patterns for files to skip during review",
    )
    focus: list[str] = Field(
        default_factory=list,
        description="Focus areas: bugs, security, performance, maintainability, tests",
    )

    # ── Validators ──────────────────────────────────────────────────────────

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in ("full", "quick", "security", "performance", "tests", "architecture"):
            raise ValueError(f"Invalid mode '{v}'. Choose from: full, quick, security, performance, tests, architecture")
        return v

    @field_validator("focus")
    @classmethod
    def validate_focus(cls, v: list[str]) -> list[str]:
        valid = {"bugs", "security", "performance", "maintainability", "tests"}
        for item in v:
            if item not in valid:
                raise ValueError(
                    f"Unknown focus area '{item}'. "
                    f"Valid options: {', '.join(sorted(valid))}"
                )
        return v


# ── Loader ────────────────────────────────────────────────────────────────────

_config_cache: ReviewConfig | None = None


def load_review_config(path: str | None = None) -> ReviewConfig:
    """
    Load ``.ai-review.yml`` from the given path or search the filesystem.

    Args:
        path: Explicit path to the YAML config file.
              If None, searches from the current working directory upward.

    Returns:
        A ReviewConfig instance (uses defaults if no file is found).
    """
    global _config_cache

    # If an explicit path is given, always reload (don't use cache).
    # For the auto-search (path=None), use the cached value.
    if path is None and _config_cache is not None:
        return _config_cache

    yaml_path = _find_config_file(path) if path else _find_config_file(None)

    if yaml_path is None:
        _config_cache = ReviewConfig()
        return _config_cache

    try:
        import yaml
    except ImportError:
        raise ImportError(
            "PyYAML is required to load .ai-review.yml. "
            "Install it: pip install pyyaml"
        )

    with open(yaml_path) as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    # Expected structure:
    #   review:
    #     mode: full
    #     max_files: 20
    #     ...
    #   ignore:
    #     - "*.lock"
    #   focus:
    #     - security
    review_block = raw.get("review", {})
    if not isinstance(review_block, dict):
        review_block = {}

    _config_cache = ReviewConfig(
        mode=review_block.get("mode", "full"),
        fail_on_high_risk=review_block.get("fail_on_high_risk", False),
        fail_on_request_changes=review_block.get("fail_on_request_changes", False),
        max_files=review_block.get("max_files", 20),
        max_patch_chars=review_block.get("max_patch_chars", 12000),
        ignore=raw.get("ignore", []),
        focus=raw.get("focus", []),
    )

    return _config_cache


# ── File finder ───────────────────────────────────────────────────────────────


def _find_config_file(path: str | None) -> str | None:
    """
    Locate a config file by path or by searching from cwd upward.

    Returns the resolved path, or None if no file is found.
    """
    if path is not None:
        if os.path.isfile(path):
            return os.path.abspath(path)
        return None

    # Search from current directory upward for CONFIG_FILENAMES
    cwd = os.getcwd()
    for filename in CONFIG_FILENAMES:
        candidate = _search_upward(cwd, filename)
        if candidate is not None:
            return candidate

    return None


def _search_upward(start_dir: str, filename: str) -> str | None:
    """Walk from start_dir up to root looking for *filename*."""
    current = os.path.abspath(start_dir)
    while True:
        candidate = os.path.join(current, filename)
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:  # reached filesystem root
            break
        current = parent
    return None
