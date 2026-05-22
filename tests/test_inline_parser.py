"""
Tests for Inline Comments Parser
=================================
Covers extraction and validation of inline code review comments from AI output.
"""
from __future__ import annotations

from app.utils.inline_parser import parse_inline_comments


# ── Valid JSON block ─────────────────────────────────────────────────────────


def test_parse_valid_single_comment():
    """A single valid inline comment should be returned."""
    review = """## Summary

Looks good.

```json
{"inline_comments": [{"path": "src/auth.py", "line": 45, "side": "RIGHT", "body": "Use bcrypt."}]}
```"""
    result = parse_inline_comments(review)
    assert len(result) == 1
    assert result[0]["path"] == "src/auth.py"
    assert result[0]["line"] == 45
    assert result[0]["side"] == "RIGHT"
    assert result[0]["body"] == "Use bcrypt."


def test_parse_multiple_comments():
    """Multiple inline comments should all be returned."""
    review = """```json
{"inline_comments": [
  {"path": "src/a.py", "line": 10, "side": "RIGHT", "body": "Fix this."},
  {"path": "src/b.py", "line": 20, "side": "LEFT", "body": "Remove this."}
]}
```"""
    result = parse_inline_comments(review)
    assert len(result) == 2
    assert result[0]["path"] == "src/a.py"
    assert result[1]["path"] == "src/b.py"


def test_parse_limits_to_max():
    """Comments beyond MAX_INLINE_COMMENTS should be ignored."""
    many_comments = [{"path": f"src/{i}.py", "line": 1, "side": "RIGHT", "body": f"Fix {i}."} for i in range(20)]
    import json
    review = f"```json\n{{\"inline_comments\": {json.dumps(many_comments)}}}\n```"
    result = parse_inline_comments(review)
    assert len(result) == 10  # MAX_INLINE_COMMENTS = 10


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_no_json_block():
    """When there is no JSON block, return empty list."""
    result = parse_inline_comments("This is a plain review.")
    assert result == []


def test_no_inline_comment_key():
    """JSON block without inline_comments key should return empty list."""
    review = """```json
{"score": 5, "risk_level": "Medium"}
```"""
    result = parse_inline_comments(review)
    assert result == []


def test_empty_comments_array():
    """Empty inline_comments array should return empty list."""
    review = """```json
{"inline_comments": []}
```"""
    result = parse_inline_comments(review)
    assert result == []


def test_skip_invalid_comment_missing_path():
    """A comment missing path should be skipped."""
    review = """```json
{"inline_comments": [
  {"line": 5, "side": "RIGHT", "body": "Fix"},
  {"path": "src/good.py", "line": 10, "side": "RIGHT", "body": "Good"}
]}
```"""
    result = parse_inline_comments(review)
    assert len(result) == 1
    assert result[0]["path"] == "src/good.py"


def test_skip_invalid_comment_missing_body():
    """A comment missing body should be skipped."""
    review = """```json
{"inline_comments": [
  {"path": "src/a.py", "line": 5, "side": "RIGHT"},
  {"path": "src/b.py", "line": 10, "side": "RIGHT", "body": "Keep"}
]}
```"""
    result = parse_inline_comments(review)
    assert len(result) == 1
    assert result[0]["path"] == "src/b.py"


def test_skip_comment_wrong_line_type():
    """A comment with non-integer line should be skipped."""
    review = """```json
{"inline_comments": [
  {"path": "src/a.py", "line": "bad", "side": "RIGHT", "body": "Nope"}
]}
```"""
    result = parse_inline_comments(review)
    assert result == []


def test_default_side_to_right():
    """When side is missing or invalid, default to RIGHT."""
    review = """```json
{"inline_comments": [
  {"path": "src/a.py", "line": 1, "body": "Default to RIGHT"}
]}
```"""
    result = parse_inline_comments(review)
    assert result[0]["side"] == "RIGHT"


def test_zero_line_skipped():
    """Line number 0 (invalid) should be skipped."""
    review = """```json
{"inline_comments": [
  {"path": "src/a.py", "line": 0, "side": "RIGHT", "body": "Zero"}
]}
```"""
    result = parse_inline_comments(review)
    assert result == []


def test_float_line_accepted():
    """A float like 5.0 should be accepted as line 5."""
    review = """```json
{"inline_comments": [
  {"path": "src/a.py", "line": 5.0, "side": "RIGHT", "body": "Five"}
]}
```"""
    result = parse_inline_comments(review)
    assert len(result) == 1
    assert result[0]["line"] == 5
