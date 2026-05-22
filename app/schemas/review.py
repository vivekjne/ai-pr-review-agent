"""
API Schemas — Pydantic Models for the FastAPI Endpoint
=======================================================
Defines request and response models for the review API.

Usage:
    @router.post("/review/pr", response_model=ReviewResponse)
    async def review_pr(body: ReviewRequest):
        ...
"""

from pydantic import BaseModel, Field, model_validator


class ReviewRequest(BaseModel):
    """
    Request body for POST /api/v1/review/pr.

    Accepts two mutually exclusive input forms:
        1. url        — full GitHub PR URL
        2. owner  +
           repo   +   — individual components
           pull_number

    Exactly one form must be provided.
    """

    url: str | None = Field(
        None,
        description="Full GitHub PR URL (e.g. https://github.com/owner/repo/pull/123)",
        examples=["https://github.com/octocat/Hello-World/pull/42"],
    )
    owner: str | None = Field(
        None,
        description="GitHub repository owner or organisation",
        examples=["octocat"],
    )
    repo: str | None = Field(
        None,
        description="GitHub repository name",
        examples=["Hello-World"],
    )
    pull_number: int | None = Field(
        None,
        description="Pull request number",
        examples=[42],
        ge=1,
    )
    post_comment: bool = Field(
        default=False,
        description="If true, post the review as a comment on the PR",
    )
    multi_agent: bool = Field(
        default=False,
        description="If true, use multi-agent review (runs 5 specialist agents + 1 final)",
    )
    mode: str = Field(
        default="full",
        description="Review focus mode: full, quick, security, performance, tests, architecture",
        examples=["full", "quick", "security", "performance", "tests", "architecture"],
    )

    @model_validator(mode="after")
    def _validate_input(self) -> "ReviewRequest":
        """Ensure exactly one input form is provided and mode is valid."""
        has_url = bool(self.url)
        has_components = bool(
            self.owner is not None
            and self.repo is not None
            and self.pull_number is not None
        )

        if not has_url and not has_components:
            raise ValueError(
                "Provide either 'url' or ('owner', 'repo', 'pull_number')"
            )
        if has_url and has_components:
            raise ValueError(
                "Provide either 'url' OR ('owner', 'repo', 'pull_number'), not both"
            )

        valid_modes = ("full", "quick", "security", "performance", "tests", "architecture")
        if self.mode not in valid_modes:
            raise ValueError(
                f"Invalid mode '{self.mode}'. Choose: {', '.join(valid_modes)}"
            )

        return self


class SkippedFile(BaseModel):
    """A file that was skipped during diff filtering with a reason."""

    filename: str = Field(
        ..., description="Path of the skipped file", examples=["package-lock.json"]
    )
    reason: str = Field(
        ..., description="Why the file was skipped", examples=["lock file"]
    )


class ReviewResponse(BaseModel):
    """Response body returned after a successful code review."""

    owner: str = Field(..., description="GitHub repository owner")
    repo: str = Field(..., description="GitHub repository name")
    pull_number: int = Field(..., description="Pull request number", ge=1)
    pr_title: str = Field(..., description="Pull request title")
    pr_url: str = Field(..., description="URL to the pull request on GitHub")
    review_markdown: str = Field(
        ..., description="The AI-generated code review in Markdown"
    )
    files_reviewed: int = Field(
        ..., description="Number of files included in the review", ge=0
    )
    files_skipped: int = Field(
        ..., description="Number of files skipped during filtering", ge=0
    )
    skipped_files: list[SkippedFile] = Field(
        default_factory=list,
        description="List of skipped files with reasons",
    )
    score: int | None = Field(
        None,
        description="Risk score 1-10 from the AI review (parsed from JSON block)",
        ge=1,
        le=10,
    )
    risk_level: str | None = Field(
        None,
        description="Risk level: Low, Medium, or High (parsed from JSON block)",
    )
    recommendation: str | None = Field(
        None,
        description="Review recommendation: Approve, Needs Manual Review, or Request Changes (parsed from JSON block)",
    )
    comment_url: str | None = Field(
        None,
        description="URL to the posted comment (only if post_comment was true)",
    )
    inline_comments: list[dict] | None = Field(
        None,
        description="Inline code review comments parsed from the AI review (if any)",
    )
    mode: str = Field(
        ..., description="Review mode used"
    )


class ErrorResponse(BaseModel):
    """Standard error response for the API."""

    detail: str = Field(
        ..., description="Human-readable error description"
    )
