"""
Tests
=====
Test suite for the AI PR Review Agent.

Test structure mirrors the app/ layout:
    tests/
        test_url_parser.py      → URL parsing
        test_github_client.py   → GitHub API client (with mocked HTTP)
        test_llm_client.py     → LLM client (with mocked API)
        test_diff_filter.py    → Diff filtering logic
        test_formatters.py     → Markdown formatting

We use pytest for all tests. Run them with:
    pytest tests/ -v
"""
