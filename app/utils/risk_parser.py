"""
Risk Parser
===========
Extracts structured risk data (score, risk level, recommendation) from
the machine-readable JSON block at the end of an AI-generated review.

The LLM is instructed to append a JSON block like this at the end:
    ```json
    {"score": 7, "risk_level": "Medium", "recommendation": "Needs Manual Review"}
    ```

This module parses that block and returns clean dict values.
If the block is missing or malformed, it falls back to None values.
"""

import json
import re
from typing import Any

# Regex to find the LAST ```json ... ``` block in the text
_JSON_BLOCK_RE = re.compile(
    r"```json\s*\n(.+?)\n\s*```", re.DOTALL
)

# Valid values for each field
VALID_RISK_LEVELS = ("Low", "Medium", "High")
VALID_RECOMMENDATIONS = ("Approve", "Needs Manual Review", "Request Changes")


def parse_risk_from_review(review_markdown: str) -> dict[str, Any]:
    """
    Extract score, risk_level, and recommendation from an AI review.

    Scans the review text for the last ```json ... ``` block and
    parses its contents.

    Args:
        review_markdown: The full Markdown response from the LLM.

    Returns:
        A dict with:
            score           (int | None): 1-10 risk score.
            risk_level      (str | None): "Low", "Medium", or "High".
            recommendation  (str | None): "Approve", "Needs Manual Review",
                                          or "Request Changes".
    """
    json_text = _extract_last_json_block(review_markdown)
    if json_text is None:
        return {"score": None, "risk_level": None, "recommendation": None}

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        return {"score": None, "risk_level": None, "recommendation": None}

    return {
        "score": _parse_score(data.get("score")),
        "risk_level": _parse_risk_level(data.get("risk_level")),
        "recommendation": _parse_recommendation(data.get("recommendation")),
    }


def _extract_last_json_block(text: str) -> str | None:
    """
    Find and return the content of the **last** ```json ... ``` block.

    Returns None if no block is found.
    """
    matches = _JSON_BLOCK_RE.findall(text)
    if not matches:
        return None
    # Return the last match
    return matches[-1].strip()


def _parse_score(value: Any) -> int | None:
    """Parse and validate a score value (1-10)."""
    if value is None:
        return None
    try:
        score = int(value)
    except (ValueError, TypeError):
        return None
    if 1 <= score <= 10:
        return score
    return None


def _parse_risk_level(value: Any) -> str | None:
    """Parse and validate a risk level value."""
    if value is None or not isinstance(value, str):
        return None
    level = value.strip()
    if level in VALID_RISK_LEVELS:
        return level
    return None


def _parse_recommendation(value: Any) -> str | None:
    """Parse and validate a recommendation value."""
    if value is None or not isinstance(value, str):
        return None
    rec = value.strip()
    if rec in VALID_RECOMMENDATIONS:
        return rec
    return None
