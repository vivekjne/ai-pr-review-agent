"""
Tests for Context Loader — Repository Review Standards
=======================================================
Covers loading of .ai-review/ guidance documents.
"""
from __future__ import annotations

import os
import tempfile

from app.services.context_loader import load_repo_standards


# ── Helpers ───────────────────────────────────────────────────────────────────


def _create_ai_review_dir(tmpdir: str) -> str:
    """Create a .ai-review/ directory inside *tmpdir* and return its path."""
    path = os.path.join(tmpdir, ".ai-review")
    os.makedirs(path, exist_ok=True)
    return path


def _write_file(directory: str, filename: str, content: str) -> str:
    """Write *content* to *filename* inside *directory* and return full path."""
    filepath = os.path.join(directory, filename)
    with open(filepath, "w") as f:
        f.write(content)
    return filepath


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_no_ai_review_folder():
    """When no .ai-review/ folder exists, return empty dict."""
    with tempfile.TemporaryDirectory() as tmpdir:
        standards = load_repo_standards(tmpdir)
        assert standards == {}


def test_empty_ai_review_folder():
    """When .ai-review/ exists but has no supported files, return empty dict."""
    with tempfile.TemporaryDirectory() as tmpdir:
        review_dir = _create_ai_review_dir(tmpdir)
        # Create an unsupported file
        _write_file(review_dir, "README.md", "# Notes")
        standards = load_repo_standards(tmpdir)
        assert standards == {}


def test_loads_single_standard():
    """A single supported file should be loaded."""
    with tempfile.TemporaryDirectory() as tmpdir:
        review_dir = _create_ai_review_dir(tmpdir)
        _write_file(review_dir, "coding-standards.md", "Use PascalCase for components.")
        standards = load_repo_standards(tmpdir)
        assert "coding-standards.md" in standards
        assert "PascalCase" in standards["coding-standards.md"]


def test_loads_all_supported_files():
    """All 5 supported files should be loaded if present."""
    with tempfile.TemporaryDirectory() as tmpdir:
        review_dir = _create_ai_review_dir(tmpdir)
        for name in ["coding-standards.md", "security-guidelines.md",
                      "frontend-guidelines.md", "backend-guidelines.md",
                      "testing-guidelines.md"]:
            _write_file(review_dir, name, f"Content for {name}")
        standards = load_repo_standards(tmpdir)
        assert len(standards) == 5
        assert standards["testing-guidelines.md"] == "Content for testing-guidelines.md"


def test_loads_partial_files():
    """Only existing files should be loaded; missing ones are ignored."""
    with tempfile.TemporaryDirectory() as tmpdir:
        review_dir = _create_ai_review_dir(tmpdir)
        _write_file(review_dir, "coding-standards.md", "Code style.")
        _write_file(review_dir, "testing-guidelines.md", "Test style.")
        standards = load_repo_standards(tmpdir)
        assert len(standards) == 2
        assert "coding-standards.md" in standards
        assert "testing-guidelines.md" in standards
        assert "security-guidelines.md" not in standards
        assert "frontend-guidelines.md" not in standards
        assert "backend-guidelines.md" not in standards


def test_ignores_unknown_files():
    """Files in .ai-review/ not in SUPPORTED_STANDARDS should be ignored."""
    with tempfile.TemporaryDirectory() as tmpdir:
        review_dir = _create_ai_review_dir(tmpdir)
        _write_file(review_dir, "coding-standards.md", "Code style.")
        _write_file(review_dir, "README.md", "Should be ignored.")
        _write_file(review_dir, "team-notes.md", "Also ignored.")
        standards = load_repo_standards(tmpdir)
        assert len(standards) == 1
        assert "coding-standards.md" in standards
        assert "README.md" not in standards


def test_skips_empty_files():
    """Files with only whitespace should be treated as empty and skipped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        review_dir = _create_ai_review_dir(tmpdir)
        _write_file(review_dir, "coding-standards.md", "")
        _write_file(review_dir, "security-guidelines.md", "   \n  \n")
        standards = load_repo_standards(tmpdir)
        assert len(standards) == 0


def test_content_preserved():
    """File content should be preserved verbatim (including formatting)."""
    content = "# Coding Standards\n\n## Naming\n- Use camelCase\n- Prefix booleans with `is`"
    with tempfile.TemporaryDirectory() as tmpdir:
        review_dir = _create_ai_review_dir(tmpdir)
        _write_file(review_dir, "coding-standards.md", content)
        standards = load_repo_standards(tmpdir)
        assert standards["coding-standards.md"] == content


def test_non_existent_path():
    """A non-existent root_path should return empty dict."""
    standards = load_repo_standards("/nonexistent/path")
    assert standards == {}
