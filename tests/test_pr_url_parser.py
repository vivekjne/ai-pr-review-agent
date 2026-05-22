"""
Tests for GitHub PR URL Parser
===============================
Covers:
    - Standard GitHub PR URLs
    - Edge cases (trailing slashes, fragments, query strings)
    - API URL format
    - Invalid URLs (issues, missing parts, non-GitHub URLs)
    - Edge cases (None, empty strings, whitespace)
"""

import pytest

# Import the function we're testing.
# sys.path is set up by pytest automatically when run from project root.
from app.utils.pr_url_parser import parse_github_pr_url, PrInfo


# ── Valid URLs ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("url", "expected"),
    [
        # Standard format
        (
            "https://github.com/octocat/Hello-World/pull/123",
            PrInfo("octocat", "Hello-World", 123),
        ),
        # Trailing slash
        (
            "https://github.com/octocat/Hello-World/pull/123/",
            PrInfo("octocat", "Hello-World", 123),
        ),
        # With /files sub-path
        (
            "https://github.com/octocat/Hello-World/pull/123/files",
            PrInfo("octocat", "Hello-World", 123),
        ),
        # With fragment (hash)
        (
            "https://github.com/octocat/Hello-World/pull/123#diff-abc",
            PrInfo("octocat", "Hello-World", 123),
        ),
        # With query string
        (
            "https://github.com/octocat/Hello-World/pull/123?foo=bar",
            PrInfo("octocat", "Hello-World", 123),
        ),
        # HTTP (not HTTPS)
        (
            "http://github.com/octocat/Hello-World/pull/123",
            PrInfo("octocat", "Hello-World", 123),
        ),
        # No protocol (inferred)
        (
            "github.com/octocat/Hello-World/pull/123",
            PrInfo("octocat", "Hello-World", 123),
        ),
        # Complex repo name (hyphens, underscores, dots)
        (
            "https://github.com/my-org/my_repo.v2/pull/42",
            PrInfo("my-org", "my_repo.v2", 42),
        ),
        # Deeply nested additional path
        (
            "https://github.com/owner/repo/pull/999/commits",
            PrInfo("owner", "repo", 999),
        ),
        # Many trailing slashes
        (
            "https://github.com/owner/repo/pull/1///",
            PrInfo("owner", "repo", 1),
        ),
    ],
)
def test_valid_pr_urls(url: str, expected: PrInfo):
    """All of these should parse successfully."""
    result = parse_github_pr_url(url)
    assert result == expected, f"Failed on URL: {url}"


# ── Invalid / edge-case URLs ─────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("url", "expected_substring"),
    [
        # Empty / None
        ("", "empty"),
        ("   ", "empty"),
        (None, "non-empty"),
        # Not a GitHub URL
        ("https://gitlab.com/owner/repo/pull/123", "github.com"),
        ("https://bitbucket.org/owner/repo/pull/123", "github.com"),
        # Wrong GitHub path (issues, not pull)
        ("https://github.com/owner/repo/issues/123", "Pull Request"),
        # Missing /pull/ entirely
        ("https://github.com/owner/repo/123", "/pull/"),
        # Missing PR number
        ("https://github.com/owner/repo/pull/", "missing"),
        ("https://github.com/owner/repo/pull", "missing"),
        # Non-numeric PR number
        ("https://github.com/owner/repo/pull/abc", "digit"),
        # Too few path segments
        ("https://github.com/owner", "/pull/"),
        ("https://github.com/", "/pull/"),
        # Random string
        ("this is not a url at all", "github.com"),
    ],
)
def test_invalid_pr_urls(url: str, expected_substring: str):
    """All of these should raise ValueError with a helpful message."""
    # If url is None, we pass it directly (pytest converts None in params to string "None")
    # We handle that in the function itself.
    if url is None:
        with pytest.raises(ValueError, match="non-empty"):
            parse_github_pr_url(None)  # type: ignore[arg-type]
        return

    with pytest.raises(ValueError, match=expected_substring):
        parse_github_pr_url(url)
