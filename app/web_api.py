"""
Web API — FastAPI Router
=========================
Provides the HTTP API for the PR review agent.

Endpoints:
    POST /api/v1/review/pr  — Run a full AI code review on a pull request

Start the server:
    uvicorn app.main:create_app --reload
"""

import logging
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from httpx import HTTPError

from app.config.settings import get_settings
from app.schemas.review import ErrorResponse, ReviewRequest, ReviewResponse, SkippedFile
from app.services.diff_filter_service import prepare_files_for_review
from app.services.github_service import (
    AuthenticationError,
    GitHubService,
    GitHubServiceError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)
from app.services.llm_service import LlmAuthError, LlmRateLimitError, LlmServiceError
from app.services.prompt_builder import build_pr_review_prompt
from app.utils.pr_url_parser import parse_github_pr_url

logger = logging.getLogger(__name__)

router = APIRouter()


# ── DELETE THE OLD ROUTER CREATION ────────────────────────────────────────────
# (There is none — this is a clean start)


@router.post(
    "/review/pr",
    response_model=ReviewResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Bad request — invalid input"},
        502: {"model": ErrorResponse, "description": "Upstream service error"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Review a GitHub pull request using AI",
    description=(
        "Accepts either a full PR URL or owner/repo/pull-number components. "
        "Fetches the PR diff from GitHub, runs an AI code review, and returns "
        "the structured Markdown review."
    ),
)
async def review_pr(request: ReviewRequest) -> ReviewResponse:
    """
    Run an AI-powered code review on a GitHub pull request.

    The endpoint supports two input forms (mutually exclusive):
        1. ``{"url": "https://github.com/owner/repo/pull/123", "mode": "full"}``
        2. ``{"owner": "octocat", "repo": "Hello-World", "pull_number": 42, "mode": "quick"}``

    Returns the review result as JSON with the review_markdown field
    containing the full AI-generated Markdown review.
    """
    # ── Step 1: Resolve owner, repo, pull_number ──────────────────────────
    if request.url:
        try:
            pr_info = parse_github_pr_url(request.url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        owner, repo, pull_number = pr_info.owner, pr_info.repo, pr_info.pull_number
    else:
        # Components validated by pydantic — guaranteed non-None here
        owner = request.owner  # type: ignore[assignment]
        repo = request.repo  # type: ignore[assignment]
        pull_number = request.pull_number  # type: ignore[assignment]

    # ── Step 2: Get settings ──────────────────────────────────────────────
    try:
        settings = get_settings()
    except SystemExit as exc:
        msg = str(exc.code) if exc.code else "Server misconfigured"
        raise HTTPException(status_code=500, detail=msg)

    # ── Step 2b: Load repo config (.ai-review.yml) ──────────────────────────
    from app.config.review_config import load_review_config

    repo_config = load_review_config()

    # Resolve effective mode: request > config > default
    effective_mode = request.mode if request.mode != "full" else repo_config.mode

    # ── Step 3: Fetch PR details ──────────────────────────────────────────
    gh = GitHubService()
    try:
        pr_details = await gh.get_pr_details(
            owner=owner,
            repo=repo,
            pull_number=pull_number,
        )
    except NotFoundError:
        raise HTTPException(
            status_code=400,
            detail=f"PR not found: {owner}/{repo}#{pull_number}",
        )
    except (AuthenticationError, PermissionDeniedError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except (RateLimitError, GitHubServiceError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # ── Step 4: Fetch changed files ───────────────────────────────────────
    try:
        pr_files = await gh.get_pr_files(
            owner=owner,
            repo=repo,
            pull_number=pull_number,
        )
    except (NotFoundError, GitHubServiceError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # ── Step 5: Filter files ──────────────────────────────────────────────
    filtered = prepare_files_for_review(
        pr_files,
        max_files=repo_config.max_files,
        max_chars=repo_config.max_patch_chars,
        custom_ignore=repo_config.ignore or None,
    )

    # ── Step 5b: Load repo standards from .ai-review/ folder ───────────────
    from app.services.context_loader import load_repo_standards

    repo_standards = load_repo_standards()

    # ── Step 6: Build prompt ──────────────────────────────────────────────
    review_prompt = build_pr_review_prompt(
        pr_details=pr_details,
        reviewable_files=filtered["reviewable_files"],
        skipped_files=filtered["skipped_files"],
        mode=effective_mode,
        focus_areas=repo_config.focus or None,
        repo_standards=repo_standards if repo_standards else None,
    )

    # ── Step 7: Call LLM ──────────────────────────────────────────────────
    from app.services.llm_service import LlmService

    llm = LlmService()
    try:
        if request.multi_agent or repo_config.multi_agent:
            from app.services.multi_agent_pipeline import run_multi_agent_review

            review_markdown = await run_multi_agent_review(
                llm=llm,
                pr_details=pr_details,
                reviewable_files=filtered["reviewable_files"],
                skipped_files=filtered["skipped_files"],
                repo_standards=repo_standards if repo_standards else None,
            )
        else:
            review_markdown = await llm.generate_pr_review(review_prompt)
    except (LlmAuthError, LlmRateLimitError, LlmServiceError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # ── Step 8a: Optionally post as comment ────────────────────────────────
    comment_url: str | None = None
    if request.post_comment:
        try:
            comment = await gh.upsert_ai_review_comment(
                owner=owner,
                repo=repo,
                pull_number=pull_number,
                review_markdown=review_markdown,
            )
            comment_url = comment.get("html_url")
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to post comment: {exc}")

    # ── Step 8b: Parse structured risk data ─────────────────────────────────
    from app.utils.risk_parser import parse_risk_from_review

    risk_data = parse_risk_from_review(review_markdown)

    # ── Step 8c: Parse inline comments and optionally post them ──────────────
    from app.utils.inline_parser import parse_inline_comments

    inline_comments = parse_inline_comments(review_markdown)
    if inline_comments and request.post_comment and comment_url:
        try:
            head_sha = pr_details.get("head_sha", "")
            await gh.create_inline_review(
                owner=owner,
                repo=repo,
                pull_number=pull_number,
                commit_id=head_sha,
                body=review_markdown,
                comments=inline_comments,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to post inline comments: {exc}")

    # ── Step 9: Build response ────────────────────────────────────────────
    skipped_items = [
        SkippedFile(filename=s["filename"], reason=s["reason"])
        for s in filtered["skipped_files"]
    ]

    return ReviewResponse(
        owner=owner,
        repo=repo,
        pull_number=pull_number,
        pr_title=pr_details.get("title", ""),
        pr_url=pr_details.get("html_url", ""),
        review_markdown=review_markdown,
        files_reviewed=filtered["reviewed_files"],
        files_skipped=filtered["skipped_count"],
        skipped_files=skipped_items,
        comment_url=comment_url,
        score=risk_data.get("score"),
        risk_level=risk_data.get("risk_level"),
        recommendation=risk_data.get("recommendation"),
        inline_comments=inline_comments if inline_comments else None,
        mode=effective_mode,
    )
