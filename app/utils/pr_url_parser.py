"""
GitHub PR URL Parser
====================
Extracts owner, repository name, and pull request number from a GitHub PR URL.

Supported URL patterns:
    • https://github.com/owner/repo/pull/123
    • https://github.com/owner/repo/pull/123/          (trailing slash)
    • https://github.com/owner/repo/pull/123/files      (sub-path is stripped)
    • https://github.com/owner/repo/pull/123#diff-xyz   (fragment is stripped)
    • https://github.com/owner/repo/pull/123?foo=bar    (query is stripped)
    • http://github.com/owner/repo/pull/123             (HTTP is allowed)
    • github.com/owner/repo/pull/123                    (protocol is inferred)
    • https://api.github.com/repos/owner/repo/pulls/123 (API URL format)

Usage:
    from app.utils.pr_url_parser import parse_github_pr_url, PrInfo

    # Returns a PrInfo NamedTuple (access fields by name)
    info = parse_github_pr_url("https://github.com/owner/repo/pull/123")
    info.owner        # → "owner"
    info.repo         # → "repo"
    info.pull_number  # → 123

    # Destructure like a tuple
    owner, repo, num = parse_github_pr_url("https://github.com/owner/repo/pull/123")

    # Convert to dict if you need JSON output
    info._asdict()  # → {"owner": "owner", "repo": "repo", "pull_number": 123}
"""

import re
from typing import NamedTuple


class PrInfo(NamedTuple):
    """
    Container for the three components extracted from a GitHub PR URL.

    Why NamedTuple?
        - Immutable — once created, values can't change (safe for passing around)
        - Lightweight — no overhead of a full class
        - Destructurable — `owner, repo, num = parse_github_pr_url(url)`
        - Dict-compatible — `info._asdict()` for JSON APIs
        - Auto-__repr__ — `PrInfo(owner='octocat', repo='Hello-World', pull_number=123)`
    """

    owner: str       # GitHub username or organisation (e.g. "octocat")
    repo: str        # Repository name (e.g. "Hello-World")
    pull_number: int # Pull request number (e.g. 123)


# ──────────────────────────────────────────────────────────────────────────────
# Regex patterns — compiled once at module load for performance.
#
# Pattern breakdown:
#   (?:https?://)?           — optional http:// or https://
#   (?:www\.)?               — optional www. prefix
#   github\.com              — the hostname (we match github.com only)
#   /                        — path separator
#   ([a-zA-Z0-9._-]+)        — owner (capture group 1)
#   /                        — separator
#   ([a-zA-Z0-9._-]+)        — repo (capture group 2)
#   /pull/                   — literally "/pull/" (not "/issues/")
#   (\d+)                    — PR number (capture group 3)
# ──────────────────────────────────────────────────────────────────────────────

_GITHUB_PR_REGEX = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/"
    r"([a-zA-Z0-9._-]+)/"        # owner
    r"([a-zA-Z0-9._-]+)/"        # repo
    r"pull/(\d+)"                # pull number
)


def parse_github_pr_url(url: str) -> PrInfo:
    """
    Parse a GitHub pull request URL and return a PrInfo NamedTuple.

    The function is lenient with:
        - Trailing slashes   (/pull/123/)
        - Extra path         (/pull/123/files)
        - URL fragments      (/pull/123#diff-abc)
        - Query strings      (/pull/123?foo=bar)

    Args:
        url: A GitHub PR URL string.

    Returns:
        A PrInfo NamedTuple with owner, repo, and pull_number.

    Raises:
        ValueError: If the URL is not a valid GitHub PR URL,
                    with a human-readable explanation.

    Examples:
        >>> info = parse_github_pr_url("https://github.com/octocat/Hello-World/pull/123")
        >>> info.owner
        'octocat'
        >>> info.repo
        'Hello-World'
        >>> info.pull_number
        123
        >>> info._asdict()
        {'owner': 'octocat', 'repo': 'Hello-World', 'pull_number': 123}
    """
    # ── Guard against None / empty input ──────────────────────────────────
    if not url or not isinstance(url, str):
        raise ValueError(
            "URL must be a non-empty string. "
            f"Got: {type(url).__name__}({url!r})"
        )

    # Strip whitespace around the URL (catches copy-paste issues)
    url = url.strip()

    if not url:
        raise ValueError("URL cannot be an empty or whitespace-only string.")

    # ── Split off fragments (#...) and query strings (?...) —──────────────
    # We only care about the path part of the URL.  Everything after # or ?
    # is semantically irrelevant for parsing the owner/repo/number.
    clean_url = url.split("#")[0].split("?")[0]

    # ── Match the regex ─────────────────────────────────────────────────────
    match = _GITHUB_PR_REGEX.search(clean_url)

    if not match:
        # Build a helpful error message depending on what went wrong
        _raise_parse_error(url)

    owner = match.group(1)
    repo = match.group(2)
    pull_number = int(match.group(3))

    return PrInfo(owner=owner, repo=repo, pull_number=pull_number)


# ──────────────────────────────────────────────────────────────────────────────
# Private helper — explains WHY parsing failed so the user can fix their input
# ──────────────────────────────────────────────────────────────────────────────

def _raise_parse_error(url: str) -> None:
    """
    Inspect the URL and raise a ValueError with a targeted message.

    This gives the user a clear hint instead of a generic "invalid URL".
    """
    url_lower = url.lower()

    # Check if it looks like a GitHub URL at all
    if "github.com" not in url_lower:
        raise ValueError(
            f"Not a GitHub URL. Expected a URL containing 'github.com', "
            f"got: {url!r}"
        )

    # Check if it has /pull/ in the path
    if "/pull/" not in url_lower:
        # Maybe it's an issue URL?
        if "/issues/" in url_lower:
            raise ValueError(
                f"This looks like a GitHub Issue URL, not a Pull Request URL. "
                f"Use '/pull/' instead of '/issues/'. URL: {url!r}"
            )
        raise ValueError(
            f"URL is missing '/pull/NNN' in the path. "
            f"A PR URL should look like: "
            f"https://github.com/owner/repo/pull/123. Got: {url!r}"
        )

    # Check if the number part is missing
    if url_lower.rstrip("/").endswith("/pull"):
        raise ValueError(
            f"PR number is missing. "
            f"A PR URL should end with a number: "
            f"https://github.com/owner/repo/pull/123. Got: {url!r}"
        )

    # Check if the number part isn't a valid integer
    pull_part = url_lower.rstrip("/").split("/pull/")[-1]
    if pull_part and not pull_part.split("/")[0].isdigit():
        raise ValueError(
            f"PR number must be a digit. "
            f"Got: {pull_part.split('/')[0]!r} in URL: {url!r}"
        )

    # Fallback generic error
    raise ValueError(
        f"Could not parse GitHub PR URL: {url!r}. "
        f"Expected format: https://github.com/owner/repo/pull/123"
    )
