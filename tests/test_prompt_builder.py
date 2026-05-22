"""
Tests for the PR Review Prompt Builder
=======================================
Covers prompt structure, mode variations, edge cases, and required sections.
"""

from __future__ import annotations

from typing import Any

from app.services.prompt_builder import build_pr_review_prompt


# ── Sample data fixtures ─────────────────────────────────────────────────────


def _pr_details(**kwargs: Any) -> dict[str, Any]:
    defaults = {
        "owner": "octocat",
        "repo": "Hello-World",
        "pull_number": 1,
        "title": "Add user authentication",
        "body": "Implements OAuth login flow.",
        "author": "alice",
        "state": "open",
        "base_branch": "main",
        "head_branch": "feat/auth",
        "created_at": "2025-01-15T10:00:00Z",
        "updated_at": "2025-01-16T12:00:00Z",
        "changed_files": 3,
        "additions": 120,
        "deletions": 30,
        "html_url": "https://github.com/octocat/Hello-World/pull/1",
    }
    defaults.update(kwargs)
    return defaults


def _file(
    filename: str,
    status: str = "modified",
    additions: int = 10,
    deletions: int = 2,
    changes: int = 12,
    patch: str = "diff --git a/src/a.py b/src/a.py\n@@ -1 +1,2 @@\n+new_line()",
    truncated: bool = False,
) -> dict[str, Any]:
    return {
        "filename": filename,
        "status": status,
        "additions": additions,
        "deletions": deletions,
        "changes": changes,
        "patch": patch,
        "raw_url": f"https://github.com/octocat/repo/raw/abc/{filename}",
        "blob_url": f"https://github.com/octocat/repo/blob/abc/{filename}",
        "truncated": truncated,
        "patch_chars": len(patch),
    }


def _skipped_file(filename: str, reason: str = "lock file") -> dict[str, str]:
    return {"filename": filename, "reason": reason}


# ── Prompt structure tests ───────────────────────────────────────────────────


def test_prompt_contains_pr_context():
    """The prompt should include PR metadata."""
    prompt = build_pr_review_prompt(_pr_details(), [_file("src/app.py")])

    assert "Add user authentication" in prompt
    assert "@alice" in prompt
    assert "feat/auth" in prompt
    assert "+120" in prompt
    assert "-30" in prompt


def test_prompt_contains_output_format():
    """The prompt should include the output Markdown structure."""
    prompt = build_pr_review_prompt(_pr_details(), [_file("src/app.py")])

    assert "# AI PR Review" in prompt
    assert "## PR Summary" in prompt
    assert "## Overall Recommendation" in prompt
    assert "## Risk Level" in prompt
    assert "## Score" in prompt
    assert "## What Changed" in prompt
    assert "## Key Findings" in prompt
    assert "## File-Level Review" in prompt
    assert "## Security Concerns" in prompt
    assert "## Performance Concerns" in prompt
    assert "## Testing Concerns" in prompt
    assert "## Maintainability Concerns" in prompt
    assert "## Skipped Files" in prompt
    assert "## Final Notes" in prompt


def test_prompt_contains_rules():
    """The prompt should include the AI review rules."""
    prompt = build_pr_review_prompt(_pr_details(), [_file("src/app.py")])

    assert "Be specific" in prompt
    assert "Do not invent" in prompt
    assert "Acknowledge uncertainty" in prompt
    assert "partial diffs" in prompt
    assert "Be constructive" in prompt
    assert "Skip empty sections" in prompt


def test_prompt_contains_file_patches():
    """Each file's diff block should appear in the prompt."""
    prompt = build_pr_review_prompt(
        _pr_details(),
        [
            _file("src/auth.py", patch="@@ -1 +1 @@\n+import jwt"),
            _file("src/utils.py"),
        ],
    )

    assert "### src/auth.py (modified, +10/-2)" in prompt
    assert "### src/utils.py (modified, +10/-2)" in prompt
    assert "+import jwt" in prompt


def test_prompt_contains_skipped_files():
    """Skipped file list should appear in the prompt."""
    skipped = [
        _skipped_file("package-lock.json", "lock file"),
        _skipped_file("dist/bundle.js", "build artifact"),
    ]
    prompt = build_pr_review_prompt(_pr_details(), [_file("src/app.py")], skipped)

    assert "package-lock.json" in prompt
    assert "lock file" in prompt
    assert "dist/bundle.js" in prompt
    assert "build artifact" in prompt


def test_prompt_skipped_files_omitted_when_empty():
    """When no files are skipped, the section should not appear."""
    prompt = build_pr_review_prompt(_pr_details(), [_file("src/app.py")])

    # The output format template contains "## Skipped Files" as a heading
    # but the actual skipped-files body should not be present.
    assert "The following files were not included" not in prompt


# ── Mode tests ────────────────────────────────────────────────────────────────


def test_full_mode_instructions():
    """Full mode should mention correctiveness and all aspects."""
    prompt = build_pr_review_prompt(_pr_details(), [_file("src/app.py")], mode="full")

    assert "comprehensive" in prompt
    assert "Correctness" in prompt
    assert "Security" in prompt
    assert "Performance" in prompt


def test_quick_mode_instructions():
    """Quick mode should mention critical/high-risk focus."""
    prompt = build_pr_review_prompt(_pr_details(), [_file("src/app.py")], mode="quick")

    assert "Critical or high-risk" in prompt
    assert "Skip minor" in prompt


def test_security_mode_instructions():
    """Security mode should mention OWASP and injection."""
    prompt = build_pr_review_prompt(
        _pr_details(), [_file("src/app.py")], mode="security"
    )

    assert "security-focused" in prompt
    assert "injection" in prompt.lower()
    assert "OWASP" in prompt


def test_performance_mode_instructions():
    """Performance mode should mention API calls, loops, and rendering."""
    prompt = build_pr_review_prompt(
        _pr_details(), [_file("src/app.py")], mode="performance"
    )

    assert "performance-focused" in prompt
    assert "API calls" in prompt
    assert "loops" in prompt
    assert "rendering" in prompt


def test_tests_mode_instructions():
    """Tests mode should mention missing tests and edge cases."""
    prompt = build_pr_review_prompt(
        _pr_details(), [_file("src/app.py")], mode="tests"
    )

    assert "testing-focused" in prompt
    assert "Missing unit" in prompt or "missing" in prompt.lower()
    assert "edge cases" in prompt.lower()


def test_architecture_mode_instructions():
    """Architecture mode should mention boundaries, coupling, and design."""
    prompt = build_pr_review_prompt(
        _pr_details(), [_file("src/app.py")], mode="architecture"
    )

    assert "architecture-focused" in prompt
    assert "boundaries" in prompt.lower()
    assert "coupling" in prompt.lower()
    assert "design patterns" in prompt.lower()


def test_mode_label_in_output_format():
    """The output format should include the review mode label."""
    prompt = build_pr_review_prompt(_pr_details(), [_file("src/app.py")])

    assert "Review Mode" in prompt
    assert "full / quick / security / performance / tests / architecture" in prompt


def test_inline_comments_section_in_prompt():
    """The output format should include the inline_comments JSON block."""
    prompt = build_pr_review_prompt(_pr_details(), [_file("src/app.py")])

    assert "inline_comments" in prompt
    assert "path" in prompt
    assert "line" in prompt
    assert "side" in prompt
    assert "body" in prompt


def test_rule_9_about_inline_comments():
    """Rule #9 about inline comments should be in the prompt."""
    prompt = build_pr_review_prompt(_pr_details(), [_file("src/app.py")])

    assert "9." in prompt
    assert "inline comments" in prompt.lower()
    assert "inline_comments" in prompt


# ── Repo standards ────────────────────────────────────────────────────────────


def test_repo_standards_section_in_prompt():
    """When repo_standards are provided, the section should appear with content."""
    standards = {"coding-standards.md": "Use camelCase for variables."}
    prompt = build_pr_review_prompt(
        _pr_details(), [_file("src/app.py")], repo_standards=standards
    )

    assert "# Repository Review Standards" in prompt
    assert "coding-standards.md" in prompt
    assert "camelCase" in prompt


def test_multiple_standards_in_prompt():
    """Multiple standard files should all appear in the prompt."""
    standards = {
        "coding-standards.md": "Use camelCase.",
        "testing-guidelines.md": "Write unit tests.",
    }
    prompt = build_pr_review_prompt(
        _pr_details(), [_file("src/app.py")], repo_standards=standards
    )

    assert "coding-standards" in prompt or "Coding Standards" in prompt
    assert "testing-guidelines" in prompt or "Testing Guidelines" in prompt


def test_no_repo_standards_section_when_empty():
    """When repo_standards is None or empty, no standards section."""
    prompt = build_pr_review_prompt(_pr_details(), [_file("src/app.py")])

    assert "# Repository Review Standards" not in prompt


def test_rule_8_appears_with_standards():
    """Rule #8 about referencing repo standards should appear when standards exist."""
    standards = {"coding-standards.md": "Use camelCase."}
    prompt = build_pr_review_prompt(
        _pr_details(), [_file("src/app.py")], repo_standards=standards
    )

    assert "8." in prompt
    assert "repository standards" in prompt.lower()


def test_rule_8_absent_without_standards():
    """Rule #8 should NOT appear when no standards are provided."""
    prompt = build_pr_review_prompt(_pr_details(), [_file("src/app.py")])

    assert "8." not in prompt


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_empty_reviewable_files():
    """When no files are reviewable, the prompt should indicate that."""
    prompt = build_pr_review_prompt(_pr_details(), [])

    assert "No reviewable changes" in prompt


def test_truncated_files_marked():
    """Files with truncated patches should include a warning."""
    patch = "x" * 100
    files = [
        _file("src/big.py", patch=patch, truncated=True),
        _file("src/small.py"),
    ]
    prompt = build_pr_review_prompt(_pr_details(), files)

    assert "[truncated]" in prompt
    assert "truncated" in prompt.lower()
    assert "src/big.py" in prompt


def test_binary_file_shows_no_diff_label():
    """A file with an empty patch should show a 'binary' label."""
    files = [_file("assets/logo.png", patch="")]
    prompt = build_pr_review_prompt(_pr_details(), files)

    assert "binary" in prompt.lower() or "no diff" in prompt.lower()


def test_skipped_in_quick_mode():
    """Quick mode should still show skipped files."""
    skipped = [_skipped_file("package-lock.json")]
    prompt = build_pr_review_prompt(
        _pr_details(), [_file("src/app.py")], skipped, mode="quick"
    )

    assert "package-lock.json" in prompt
    assert "focused code review" in prompt
    assert "Critical or high-risk" in prompt


# ── PR context completeness ────────────────────────────────────────────────────


def test_pr_context_all_fields():
    """All required PR context fields should be present."""
    details = _pr_details(
        title="Add auth",
        author="bob",
        head_branch="feature/login",
        state="open",
        changed_files=5,
        additions=200,
        deletions=50,
    )
    prompt = build_pr_review_prompt(details, [_file("src/app.py")])

    assert "Add auth" in prompt
    assert "@bob" in prompt
    assert "feature/login" in prompt
    assert "200" in prompt
    assert "50" in prompt
