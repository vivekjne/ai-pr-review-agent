"""
Tests for Risk Parser
=====================
Covers extraction of structured risk data from AI review Markdown.
"""

from __future__ import annotations

from app.utils.risk_parser import parse_risk_from_review


# ── Valid JSON block ─────────────────────────────────────────────────────────


def test_parse_valid_json():
    """A properly formatted JSON block should return correct values."""
    review = """## Summary

Looks good.

```json
{"score": 8, "risk_level": "High", "recommendation": "Request Changes"}
```"""
    result = parse_risk_from_review(review)
    assert result["score"] == 8
    assert result["risk_level"] == "High"
    assert result["recommendation"] == "Request Changes"


def test_parse_low_risk():
    """Low risk values should parse correctly."""
    review = """```json
{"score": 2, "risk_level": "Low", "recommendation": "Approve"}
```"""
    result = parse_risk_from_review(review)
    assert result["score"] == 2
    assert result["risk_level"] == "Low"
    assert result["recommendation"] == "Approve"


def test_parse_medium_risk_needs_manual():
    """Medium risk with Needs Manual Review."""
    review = """```json
{"score": 5, "risk_level": "Medium", "recommendation": "Needs Manual Review"}
```"""
    result = parse_risk_from_review(review)
    assert result["score"] == 5
    assert result["risk_level"] == "Medium"
    assert result["recommendation"] == "Needs Manual Review"


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_parse_no_json_block():
    """When there is no JSON block, return None values."""
    review = "This is a simple review with no JSON block at the end."
    result = parse_risk_from_review(review)
    assert result["score"] is None
    assert result["risk_level"] is None
    assert result["recommendation"] is None


def test_parse_empty_string():
    """An empty string should return None values."""
    result = parse_risk_from_review("")
    assert result["score"] is None
    assert result["risk_level"] is None
    assert result["recommendation"] is None


def test_parse_malformed_json():
    """Malformed JSON inside the block should return None values."""
    review = """Some review.

```json
{invalid json here
```"""
    result = parse_risk_from_review(review)
    assert result["score"] is None
    assert result["risk_level"] is None
    assert result["recommendation"] is None


def test_parse_last_of_multiple_blocks():
    """When multiple JSON blocks exist, use the LAST one."""
    review = """```json
{"score": 1, "risk_level": "Low", "recommendation": "Approve"}
```

Some text.

```json
{"score": 9, "risk_level": "High", "recommendation": "Request Changes"}
```"""
    result = parse_risk_from_review(review)
    assert result["score"] == 9
    assert result["risk_level"] == "High"
    assert result["recommendation"] == "Request Changes"


def test_parse_extra_fields_ignored():
    """Additional JSON fields beyond the three should be ignored."""
    review = """```json
{"score": 6, "risk_level": "Medium", "recommendation": "Needs Manual Review", "extra": "ignored"}
```"""
    result = parse_risk_from_review(review)
    assert result["score"] == 6
    assert result["risk_level"] == "Medium"
    assert result["recommendation"] == "Needs Manual Review"


def test_parse_wrong_types():
    """Wrong types for fields should return None for those fields."""
    review = """```json
{"score": "not-a-number", "risk_level": 123, "recommendation": null}
```"""
    result = parse_risk_from_review(review)
    assert result["score"] is None
    assert result["risk_level"] is None
    assert result["recommendation"] is None


def test_parse_score_out_of_range():
    """Score outside 1-10 should return None."""
    review = """```json
{"score": 99, "risk_level": "Low", "recommendation": "Approve"}
```"""
    result = parse_risk_from_review(review)
    assert result["score"] is None
    assert result["risk_level"] == "Low"
    assert result["recommendation"] == "Approve"


def test_parse_invalid_risk_level():
    """Risk level not in valid set should return None."""
    review = """```json
{"score": 5, "risk_level": "Critical", "recommendation": "Approve"}
```"""
    result = parse_risk_from_review(review)
    assert result["score"] == 5
    assert result["risk_level"] is None
    assert result["recommendation"] == "Approve"


def test_parse_review_with_markdown_around_json():
    """The JSON block should be parseable even with surrounding markdown."""
    review = """## Final Notes

Overall this PR looks solid but has a few concerns.

---

```json
{"score": 4, "risk_level": "Low", "recommendation": "Approve"}
```"""
    result = parse_risk_from_review(review)
    assert result["score"] == 4
    assert result["risk_level"] == "Low"
    assert result["recommendation"] == "Approve"
