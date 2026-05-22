"""
Inline Comments Parser
======================
Extracts machine-readable inline code review comments from the LLM's output.

The LLM is instructed to produce an `inline_comments` JSON block alongside
the main Markdown review.  Each comment in the array specifies:
    - path (str): filename from the diff
    - line (int): line number in the file
    - side (str): "RIGHT" for new code, "LEFT" for deleted code
    - body (str): 1–3 sentence suggestion

This module validates and normalises these comments for use with the
GitHub Pull Request Review API.

Usage:
    from app.utils.inline_parser import parse_inline_comments

    comments = parse_inline_comments(review_markdown)
    for c in comments:
        print(f"{c['path']}:{c['line']} — {c['body']}")
"""

import json
import re
from typing import Any

# Regex to find the LAST ```json block — shared with risk_parser
_JSON_BLOCK_RE = re.compile(r"```json\s*\n(.+?)\n\s*```", re.DOTALL)

# Max inline comments to accept (prevents prompt abuse)
MAX_INLINE_COMMENTS = 10


def parse_inline_comments(review_markdown: str) -> list[dict[str, Any]]:
    """
    Extract and validate inline comments from an AI review.

    Scans the review text for the last `` ```json ... ``` `` block,
    looks for an ``inline_comments`` array, and returns validated
    comment dicts.

    Args:
        review_markdown: The full Markdown response from the LLM.

    Returns:
        A list of validated comment dicts.  Each dict has:
            path (str):     Filename.
            line (int):     Line number.
            side (str):     "LEFT" or "RIGHT".
            body (str):     Comment text.
        Returns an empty list if no valid inline comments are found.
    """
    json_text = _extract_last_json_block(review_markdown)
    if json_text is None:
        return []

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        return []

    raw_comments: list[dict[str, Any]] | Any = data.get("inline_comments")
    if not raw_comments or not isinstance(raw_comments, list):
        return []

    validated: list[dict[str, Any]] = []
    for raw in raw_comments[:MAX_INLINE_COMMENTS]:
        comment = _validate_comment(raw)
        if comment is not None:
            validated.append(comment)

    return validated


# ── Internal helpers ──────────────────────────────────────────────────────────


def _extract_last_json_block(text: str) -> str | None:
    """Return the content of the last ```json ... ``` block, or None."""
    matches = _JSON_BLOCK_RE.findall(text)
    if not matches:
        return None
    return matches[-1].strip()


def _validate_comment(raw: Any) -> dict[str, Any] | None:
    """Validate a single raw comment dict and return a normalised version."""
    if not isinstance(raw, dict):
        return None

    path = raw.get("path")
    if not isinstance(path, str) or not path.strip():
        return None
    path = path.strip()

    line = raw.get("line")
    if not isinstance(line, int) or line < 1:
        # Accept float that represents a whole number
        if isinstance(line, float) and line == int(line) and line >= 1:
            line = int(line)
        else:
            return None

    side = raw.get("side", "RIGHT")
    if side not in ("LEFT", "RIGHT"):
        side = "RIGHT"

    body = raw.get("body")
    if not isinstance(body, str) or not body.strip():
        return None
    body = body.strip()

    return {
        "path": path,
        "line": line,
        "side": side,
        "body": body,
    }
