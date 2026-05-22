"""
Context Loader — Repository Review Standards
=============================================
Loads lightweight guidance documents from the ``.ai-review/`` folder
in the repository root and makes them available for inclusion in the
AI review prompt.

Supported files:
    .ai-review/coding-standards.md
    .ai-review/security-guidelines.md
    .ai-review/frontend-guidelines.md
    .ai-review/backend-guidelines.md
    .ai-review/testing-guidelines.md

Usage:
    from app.services.context_loader import load_repo_standards

    standards = load_repo_standards()
    if standards:
        prompt = build_pr_review_prompt(..., repo_standards=standards)
"""

import os

# ── Supported filenames in .ai-review/ ───────────────────────────────────────
# Files outside this list are ignored (keeps the system predictable).
SUPPORTED_STANDARDS: list[str] = [
    "coding-standards.md",
    "security-guidelines.md",
    "frontend-guidelines.md",
    "backend-guidelines.md",
    "testing-guidelines.md",
]

# Directory name to search for
REVIEW_DIR = ".ai-review"


def load_repo_standards(root_path: str | None = None) -> dict[str, str]:
    """
    Load repository review standards from the ``.ai-review/`` folder.

    Looks for the folder in ``root_path`` if given, otherwise in the
    current working directory.  Only loads files from the
    ``SUPPORTED_STANDARDS`` list.

    Args:
        root_path: Explicit path to search for .ai-review/.
                   If None, uses ``os.getcwd()``.

    Returns:
        A dict mapping the standard filename (without path) to its
        file content.  Returns an empty dict if no .ai-review/ folder
        or none of the supported files are present.
    """
    base = os.path.abspath(root_path) if root_path else os.getcwd()
    review_dir = os.path.join(base, REVIEW_DIR)

    if not os.path.isdir(review_dir):
        return {}

    standards: dict[str, str] = {}

    for filename in SUPPORTED_STANDARDS:
        filepath = os.path.join(review_dir, filename)
        if os.path.isfile(filepath):
            try:
                with open(filepath, encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    standards[filename] = content
            except OSError:
                # Skip files that can't be read (permissions, etc.)
                continue

    return standards
