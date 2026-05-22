"""
Application Entry Point
=======================
Wires together configuration, services, and exposes them through:

    1. CLI — ``python -m app.main`` (Typer — runs PR review from terminal)
    2. API — ``uvicorn app.main:create_app --reload`` (FastAPI web server)

Both modes share the same underlying services (GitHub client, LLM client,
review engine), so behaviour is consistent regardless of how you invoke it.
"""

import os
import sys

# ──────────────────────────────────────────────────────────────────────────────
# Ensure the project root is on sys.path so that `import app` works reliably
# regardless of whether we run as `python -m app.main` or `python app/main.py`
# ──────────────────────────────────────────────────────────────────────────────
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


# ── CLI mode ─────────────────────────────────────────────────────────────────


def main():
    """
    CLI entry point — delegates to the Typer app in cli/.

    Usage:
        python -m app.main --url https://github.com/owner/repo/pull/123
        python -m app.main --owner octocat --repo Hello-World --pull-number 42
    """
    from app.cli.review_pr import cli_app

    cli_app()


# ── Web API mode (FastAPI) ────────────────────────────────────────────────────


def create_app():
    """
    Factory for the FastAPI application.

    Usage:
        uvicorn app.main:create_app --reload
    """
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from app.web_api import router

    app = FastAPI(
        title="AI PR Review Agent",
        version="0.1.0",
        description="Automatically reviews GitHub pull requests using AI.",
    )

    # ── CORS — allow all origins (safe for local / internal use) ───────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Health check ───────────────────────────────────────────────────────
    @app.get("/health", tags=["system"])
    async def health():
        """Simple health-check endpoint for monitoring / load balancers."""
        return {"status": "ok"}

    # ── Mount the review API router ────────────────────────────────────────
    app.include_router(router, prefix="/api/v1")

    return app


# ──────────────────────────────────────────────────────────────────────────────
# Script behaviour
#   • When run as `python app/main.py` → run the CLI
#   • When imported by uvicorn        → expose create_app factory
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
