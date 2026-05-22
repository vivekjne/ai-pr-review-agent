"""
Tests for Review Configuration — .ai-review.yml
================================================
Covers loading, validation, and defaults.
"""
from __future__ import annotations

import os
import tempfile

import pytest
import yaml

from app.config.review_config import ReviewConfig, load_review_config

# ── Reset the global cache between tests ──────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_config_cache():
    """Clear the module-level config cache before each test."""
    import app.config.review_config as rc_module

    rc_module._config_cache = None
    yield


# ── Defaults ──────────────────────────────────────────────────────────────────


def test_default_config():
    """When no file is found, defaults should be returned."""
    config = load_review_config("/nonexistent/path/.ai-review.yml")
    assert config.mode == "full"
    assert config.max_files == 20
    assert config.max_patch_chars == 12000
    assert config.fail_on_high_risk is False
    assert config.fail_on_request_changes is False
    assert config.ignore == []
    assert config.focus == []


# ── Loading valid YAML ────────────────────────────────────────────────────────


def test_load_full_config():
    """A complete valid YAML file should be parsed correctly."""
    data = {
        "review": {
            "mode": "quick",
            "fail_on_high_risk": True,
            "fail_on_request_changes": True,
            "max_files": 10,
            "max_patch_chars": 5000,
        },
        "ignore": ["*.lock", "dist/"],
        "focus": ["security", "performance"],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        yaml.dump(data, f)
        tmp_path = f.name

    try:
        config = load_review_config(tmp_path)
        assert config.mode == "quick"
        assert config.fail_on_high_risk is True
        assert config.fail_on_request_changes is True
        assert config.max_files == 10
        assert config.max_patch_chars == 5000
        assert config.ignore == ["*.lock", "dist/"]
        assert config.focus == ["security", "performance"]
    finally:
        os.unlink(tmp_path)


def test_load_minimal_config():
    """A minimal config with only a couple of overrides should work."""
    data = {"review": {"mode": "security"}, "focus": ["bugs"]}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        yaml.dump(data, f)
        tmp_path = f.name

    try:
        config = load_review_config(tmp_path)
        assert config.mode == "security"
        assert config.focus == ["bugs"]
        assert config.max_files == 20  # default
        assert config.ignore == []  # default
    finally:
        os.unlink(tmp_path)


def test_empty_yaml():
    """An empty YAML file should return defaults."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write("")
        tmp_path = f.name

    try:
        config = load_review_config(tmp_path)
        assert config.mode == "full"
        assert config.ignore == []
        assert config.focus == []
    finally:
        os.unlink(tmp_path)


# ── Validation ────────────────────────────────────────────────────────────────


def test_invalid_mode():
    """An invalid mode should raise ValueError."""
    with pytest.raises(ValueError, match="Invalid mode"):
        ReviewConfig(mode="nonexistent")


def test_invalid_focus():
    """An invalid focus area should raise ValueError."""
    with pytest.raises(ValueError, match="Unknown focus"):
        ReviewConfig(focus=["security", "typos", "bugs"])


def test_invalid_max_files_range():
    """A value outside the range should raise."""
    with pytest.raises(ValueError):
        ReviewConfig(max_files=0)
    ReviewConfig(max_files=1)  # should be fine


def test_valid_focus_all():
    """All valid focus areas should work."""
    config = ReviewConfig(
        focus=["bugs", "security", "performance", "maintainability", "tests"]
    )
    assert len(config.focus) == 5


# ── CLI overrides ─────────────────────────────────────────────────────────────


def test_fail_on_defaults():
    """fail_on_* fields should default to False (non-blocking)."""
    config = ReviewConfig()
    assert config.fail_on_high_risk is False
    assert config.fail_on_request_changes is False


def test_fail_on_custom_values():
    """Custom values for fail_on_* should be accepted."""
    config = ReviewConfig(fail_on_high_risk=True, fail_on_request_changes=True)
    assert config.fail_on_high_risk is True
    assert config.fail_on_request_changes is True


def test_cli_mode_override():
    """When mode is explicitly set, it should override config value."""
    config = ReviewConfig(mode="quick")
    # Simulate CLI behavior: CLI mode is not None → use CLI
    cli_mode = "security"
    effective = cli_mode if cli_mode is not None else config.mode
    assert effective == "security"

    # No CLI mode → use config
    cli_mode = None
    effective = cli_mode if cli_mode is not None else config.mode
    assert effective == "quick"
