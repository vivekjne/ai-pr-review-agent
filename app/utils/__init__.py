"""
Utilities Module
================
Shared helpers that don't belong to a specific service.

Utilities in this package:
    pr_url_parser.py  → Extract owner/repo/pull_number from a GitHub PR URL
    diff_filter.py    → Filter and truncate diffs before sending to the LLM
    formatters.py     → Convert raw LLM output into structured Markdown
    risk_parser.py    → Extract score, risk_level, recommendation from review JSON
    inline_parser.py  → Extract inline code review comments from review JSON
"""
