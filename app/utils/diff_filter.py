"""
Diff Filter
===========
Filters and truncates PR diffs before sending them to the LLM.

Why filter?
    - PRs can contain hundreds of files (binary files, lockfiles, generated code)
    - LLMs have context windows — huge diffs get truncated or cause errors
    - We want high-quality reviews, not noisy ones

What gets filtered:
    - Binary files (GitHub returns patch=None for these)
    - Generated/lock files (package-lock.json, *.min.js, etc.)
    - Files exceeding the per-file patch size limit
    - Files beyond the MAX_FILES_TO_REVIEW limit
"""

# File patterns to always skip — these add noise without review value
SKIP_PATTERNS: list[str] = [
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Gemfile.lock",
    "poetry.lock",
    "*.min.js",
    "*.min.css",
    "*.map",
]


def filter_files(files: list[dict], max_files: int, max_chars: int) -> list[dict]:
    """
    Filter and truncate the list of changed files from a PR.

    Args:
        files:    Raw response from GET /repos/.../pulls/{number}/files
        max_files: Maximum number of files to include
        max_chars: Maximum total characters for all patches combined

    Returns:
        Filtered list of file dicts, ready to send to the LLM.
    """
    # TODO: Milestone 7
    # 1. Skip files where patch is None (binary files)
    # 2. Skip files matching any SKIP_PATTERNS
    # 3. Sort by patch length (shortest first — we want to review as much as possible)
    # 4. Truncate to max_files
    # 5. Truncate total patch characters to max_chars
    # 6. Return the filtered list
    raise NotImplementedError("To be implemented in Milestone 7")
