"""
CLI Module
==========
Command-line interface built with Typer.

Typer is a modern CLI framework that:
    • Uses Python type hints for automatic argument/help parsing
    • Supports subcommands (like `git commit`, `git push`)
    • Integrates with Rich for pretty terminal output

Modules:
    review_pr.py → The main CLI handler (--url or owner/repo/pull-number)
"""

from app.cli.review_pr import cli_app  # noqa: F401 — re-exported for convenience
