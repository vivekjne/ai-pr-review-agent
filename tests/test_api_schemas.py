"""
Tests for the FastAPI Pydantic Schemas
=======================================
Tests the request/response validation for the review API endpoint.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.review import ReviewRequest, ReviewResponse, SkippedFile


# ── ReviewRequest validation ──────────────────────────────────────────────────


def test_request_url_only():
    """A request with only a url should be valid."""
    request = ReviewRequest(url="https://github.com/owner/repo/pull/123")
    assert request.url == "https://github.com/owner/repo/pull/123"
    assert request.mode == "full"  # default


def test_request_components_only():
    """A request with owner+repo+pull_number should be valid."""
    request = ReviewRequest(owner="octocat", repo="Hello-World", pull_number=42)
    assert request.owner == "octocat"
    assert request.repo == "Hello-World"
    assert request.pull_number == 42


def test_request_both_url_and_components():
    """Providing both url and components should raise validation error."""
    with pytest.raises(ValidationError, match="not both"):
        ReviewRequest(
            url="https://github.com/owner/repo/pull/1",
            owner="o",
            repo="r",
            pull_number=1,
        )


def test_request_neither():
    """Providing neither url nor components should raise validation error."""
    with pytest.raises(ValidationError, match="Provide either"):
        ReviewRequest()  # type: ignore[call-arg]


def test_request_partial_components():
    """Only some components without url should raise validation error."""
    with pytest.raises(ValidationError, match="Provide either"):
        ReviewRequest(owner="o", repo="r")  # missing pull_number


def test_request_invalid_mode():
    """An invalid mode should raise validation error."""
    with pytest.raises(ValidationError, match="Invalid mode"):
        ReviewRequest(
            url="https://github.com/owner/repo/pull/1",
            mode="nonexistent",
        )


def test_request_mode_case_sensitive():
    """Mode should be case-sensitive."""
    request = ReviewRequest(url="https://github.com/owner/repo/pull/1", mode="full")
    assert request.mode == "full"

    request = ReviewRequest(url="https://github.com/owner/repo/pull/1", mode="quick")
    assert request.mode == "quick"

    request = ReviewRequest(url="https://github.com/owner/repo/pull/1", mode="security")
    assert request.mode == "security"

    request = ReviewRequest(url="https://github.com/owner/repo/pull/1", mode="performance")
    assert request.mode == "performance"

    request = ReviewRequest(url="https://github.com/owner/repo/pull/1", mode="tests")
    assert request.mode == "tests"

    request = ReviewRequest(url="https://github.com/owner/repo/pull/1", mode="architecture")
    assert request.mode == "architecture"


def test_request_pull_number_must_be_positive():
    """Pull number should be >= 1."""
    with pytest.raises(ValidationError):
        ReviewRequest(owner="o", repo="r", pull_number=0)


# ── ReviewResponse ────────────────────────────────────────────────────────────


def test_response_requires_all_fields():
    """ReviewResponse should require all non-default fields."""
    with pytest.raises(ValidationError):
        ReviewResponse()  # type: ignore[call-arg]


def test_response_with_minimal_data():
    """A well-formed response should work."""
    response = ReviewResponse(
        owner="octocat",
        repo="Hello-World",
        pull_number=42,
        pr_title="Add auth",
        pr_url="https://github.com/octocat/Hello-World/pull/42",
        review_markdown="## Review\n\nLooks good!",
        files_reviewed=3,
        files_skipped=1,
        skipped_files=[SkippedFile(filename="lock.json", reason="lock file")],
        mode="full",
    )
    assert response.owner == "octocat"
    assert len(response.skipped_files) == 1
    assert response.skipped_files[0].filename == "lock.json"
    assert response.mode == "full"
