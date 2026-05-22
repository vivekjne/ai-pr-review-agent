"""
AI PR Review Agent
==================
A tool that reviews GitHub pull requests using AI (LLM via OpenCode Go).

Modes of operation:
    1. CLI — run from your terminal for one-off reviews
    2. API — FastAPI server for integration with other tools
    3. CI/CD — GitHub Action that runs automatically on every PR

Package layout:
    cli/        → Typer command-line interface
    config/     → Settings & environment loading
    services/   → Core business logic (GitHub API, LLM, review pipeline)
    schemas/    → Pydantic models (request/response validation)
    utils/      → Shared helpers (URL parsing, diff filtering, formatting)
"""

__version__ = "0.1.0"
