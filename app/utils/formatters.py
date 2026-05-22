"""
Output Formatters
=================
Converts raw LLM responses and PR data into structured, GitHub-friendly output.

Key outputs:
    - Markdown review (for PR comments and CLI display)
    - Plain text summary (for terminal output)
    - JSON report (for API responses)
"""


def format_review_as_markdown(review_text: str, pr_info: dict | None = None) -> str:
    """
    Wrap the raw LLM review text in a consistent markdown template.

    The template includes:
        - A header with meta-info about the PR
        - The LLM's review (already in markdown)
        - A footer with stats and disclaimers

    Args:
        review_text: Raw markdown response from the LLM
        pr_info:     Optional dict with PR metadata (title, author, file count)

    Returns:
        Polished markdown string ready for a PR comment.
    """
    # TODO: Milestone 12
    raise NotImplementedError("To be implemented in Milestone 12")


def count_severities(review_text: str) -> dict[str, int]:
    """
    Count how many findings of each severity appear in the review.

    Returns a dict like: {"critical": 2, "warning": 5, "suggestion": 3}

    This is useful for the review summary table and for risk scoring.
    """
    # TODO: Milestone 12
    raise NotImplementedError
