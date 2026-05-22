"""
Diff Filter Service
===================
Filters and prioritises PR changed files before sending them to the LLM.

Why filter?
    - PRs can contain lock files, minified bundles, coverage — noise for the LLM
    - LLMs have finite context windows — huge diffs get truncated or cost too much
    - We want to maximise the value-per-token of every review

Pipeline:
    1. Categorise every file as reviewable or skipped (with a reason)
    2. Sort reviewable files by patch size (smallest first)
    3. Apply MAX_FILES_TO_REVIEW cap
    4. Apply MAX_PATCH_CHARS cumulative budget (truncate oversized patches)

Usage:
    from app.services.diff_filter_service import prepare_files_for_review
    result = prepare_files_for_review(pr_files, max_files=20, max_chars=12000)
    for f in result["reviewable_files"]:
        print(f["filename"], f.get("truncated", False))
    for s in result["skipped_files"]:
        print(f"SKIPPED {s['filename']}: {s['reason']}")
"""

import fnmatch
from typing import Any

# ── Skip Patterns ─────────────────────────────────────────────────────────────
# Each pattern is either:
#   - A literal filename   → matched against the final path component
#   - A wildcard path      → matched with fnmatch against the full path

LOCK_FILE_PATTERNS: list[str] = [
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "Gemfile.lock",
]

ARTIFACT_PATTERNS: list[str] = [
    "dist/*",
    "build/*",
    "coverage/*",
]

MINIFIED_PATTERNS: list[str] = [
    "*.min.js",
    "*.min.css",
    "*.map",
]


# ── Public API ────────────────────────────────────────────────────────────────


def prepare_files_for_review(
    files: list[dict[str, Any]],
    max_files: int = 20,
    max_chars: int = 12000,
    custom_ignore: list[str] | None = None,
) -> dict[str, Any]:
    """
    Categorise, filter, and truncate changed files for LLM review.

    Args:
        files:     List of file dicts returned by GitHubService.get_pr_files().
        max_files: Maximum number of reviewable files (MAX_FILES_TO_REVIEW).
        max_chars: Cumulative character budget for all patches (MAX_PATCH_CHARS).
        custom_ignore: Additional glob patterns to skip (from .ai-review.yml).

    Returns:
        A dict with:
            reviewable_files : list of file dicts enriched with
                truncated (bool) and patch_chars (int).
            skipped_files    : list of {filename, reason} dicts.
            total_files      : int — original input count.
            reviewed_files   : int — reviewable count.
            skipped_count    : int — skipped count.
    """
    # ── Phase 1: categorise every file ─────────────────────────────────────
    reviewable: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for f in files:
        filename = f.get("filename", "")
        # Normalise path separators to forward slash for consistent matching
        norm_path = filename.replace("\\", "/")
        leaf = norm_path.rsplit("/", 1)[-1] if "/" in norm_path else norm_path

        reason = _skip_reason(leaf, norm_path, f.get("patch", ""), custom_ignore)

        if reason:
            skipped.append({"filename": filename, "reason": reason})
        else:
            reviewable.append(dict(f))  # shallow copy — safe for simple types

    # ── Phase 2: sort by patch length (ascending) ──────────────────────────
    # Smaller patches first = more files reviewed within the same character budget
    reviewable.sort(key=lambda f: len(f.get("patch", "")))

    # ── Phase 3 & 4: apply limits ─────────────────────────────────────────
    limited_reviewable: list[dict[str, Any]] = []
    remaining_budget = max_chars

    for i, f in enumerate(reviewable):
        # 3a. MAX_FILES_TO_REVIEW — first N files get a chance
        if i >= max_files:
            skipped.append({"filename": f["filename"], "reason": "too large"})
            continue

        patch_len = len(f.get("patch", ""))

        if patch_len == 0:
            # Binary/empty patch — no character cost, always include
            f["truncated"] = False
            f["patch_chars"] = 0
            limited_reviewable.append(f)
            continue

        # 4. Character budget — cumulative across all files.
        #    If a file doesn't fit, skip it entirely so remaining budget
        #    can be used for the next (smaller) file.
        if patch_len <= remaining_budget:
            f["truncated"] = False
            f["patch_chars"] = patch_len
            remaining_budget -= patch_len
            limited_reviewable.append(f)
        else:
            skipped.append({"filename": f["filename"], "reason": "too large"})

    # ── Build result ───────────────────────────────────────────────────────
    return {
        "reviewable_files": limited_reviewable,
        "skipped_files": skipped,
        "total_files": len(files),
        "reviewed_files": len(limited_reviewable),
        "skipped_count": len(skipped),
    }


# ── Internal helpers ──────────────────────────────────────────────────────────


def _skip_reason(
    leaf: str,
    norm_path: str,
    patch: str,
    custom_patterns: list[str] | None = None,
) -> str | None:
    """
    Return a skip reason string, or None if the file is reviewable.

    Args:
        leaf:           Base filename (last path component).
        norm_path:      Full normalized path.
        patch:          The diff patch text (empty for binary files).
        custom_patterns: Additional glob patterns from .ai-review.yml.

    Checks are ordered from most-specific to most-general so that a file
    receives the most descriptive reason when it matches multiple patterns.
    """
    # 1. Generated files — check the full path
    if "generated" in norm_path.lower():
        return "generated"

    # 2. Lock files
    if leaf in LOCK_FILE_PATTERNS:
        return "lock file"

    # 3. Minified / source map
    for pattern in MINIFIED_PATTERNS:
        if fnmatch.fnmatch(leaf, pattern):
            if leaf.endswith(".map"):
                return "source map"
            return "minified"

    # 4. Build / dist / coverage directory
    for pattern in ARTIFACT_PATTERNS:
        if fnmatch.fnmatch(norm_path, pattern) or norm_path.startswith(
            pattern.rstrip("/*")
        ):
            return "build artifact"

    # 5. Custom ignore patterns from .ai-review.yml
    if custom_patterns:
        for pattern in custom_patterns:
            if fnmatch.fnmatch(leaf, pattern) or fnmatch.fnmatch(norm_path, pattern):
                return "custom ignore"

    # 6. Binary (no patch content)
    if not patch:
        return "binary"

    # ── Reviewable ─────────────────────────────────────────────────────────
    return None
