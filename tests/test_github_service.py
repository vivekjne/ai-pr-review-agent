"""
Tests for the GitHub API Service
=================================
Uses unittest.mock to patch httpx so no real network calls are made.

We test:
    - Successful PR details fetch and normalisation
    - Each error code → the correct exception type and message
    - Rate-limiting detection (both 429 and 403-with-body)
    - Token loading from settings when not explicitly provided
    - PR files fetch, normalisation, binary files, and pagination
    - Link header parsing for pagination
    - PR comments: list, create, update, upsert
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from pydantic import SecretStr

from app.services.github_service import (
    AuthenticationError,
    GitHubService,
    GitHubServiceError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def service() -> GitHubService:
    """A GitHubService with a dummy token — no env needed."""
    return GitHubService(token=SecretStr("ghp_test_fake_token"))


@pytest.fixture
def mock_pr_response() -> dict[str, Any]:
    """Simulated response from GET /repos/owner/repo/pulls/1."""
    return {
        "title": "Add login feature",
        "body": "Implements OAuth-based login.",
        "user": {"login": "alice"},
        "state": "open",
        "base": {"ref": "main"},
        "head": {"ref": "feature/login"},
        "created_at": "2025-01-15T10:00:00Z",
        "updated_at": "2025-01-16T12:30:00Z",
        "changed_files": 5,
        "additions": 120,
        "deletions": 30,
        "html_url": "https://github.com/owner/repo/pull/1",
    }


@pytest.fixture
def mock_files_response() -> list[dict[str, Any]]:
    """Simulated response from GET /repos/owner/repo/pulls/1/files."""
    return [
        {
            "filename": "src/auth.py",
            "status": "modified",
            "additions": 45,
            "deletions": 10,
            "changes": 55,
            "patch": "@@ -1,5 +1,10 @@\n+import jwt\n def login():",
            "raw_url": "https://github.com/owner/repo/raw/abc123/src/auth.py",
            "blob_url": "https://github.com/owner/repo/blob/abc123/src/auth.py",
        },
        {
            "filename": "src/utils.py",
            "status": "added",
            "additions": 20,
            "deletions": 0,
            "changes": 20,
            "patch": "@@ -0,0 +1,20 @@\n+def helper():",
            "raw_url": "https://github.com/owner/repo/raw/abc123/src/utils.py",
            "blob_url": "https://github.com/owner/repo/blob/abc123/src/utils.py",
        },
        {
            "filename": "assets/logo.png",
            "status": "modified",
            "additions": 0,
            "deletions": 0,
            "changes": 0,
            "raw_url": "https://github.com/owner/repo/raw/abc123/assets/logo.png",
            "blob_url": "https://github.com/owner/repo/blob/abc123/assets/logo.png",
        },
    ]


# ── Helper to build a mock response with optional Link header ─────────────────


def build_mock_response(status_code: int, json_body: Any, link: str | None = None) -> Mock:
    """Return a Mock that simulates an httpx.Response."""
    mock_resp = Mock(spec=httpx.Response)
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_body
    mock_resp.is_success = 200 <= status_code < 300
    mock_resp.text = str(json_body)
    mock_resp.headers = {
        "X-RateLimit-Remaining": "4999",
        "X-RateLimit-Reset": str(int(datetime.now(timezone.utc).timestamp()) + 3600),
    }
    if link:
        mock_resp.headers["Link"] = link
    return mock_resp


def _mock_client_request(status_code: int, json_body: Any, link: str | None = None) -> AsyncMock:
    """Return an AsyncMock that simulates ``client.request()`` or ``client.post()`` etc."""
    mock_resp = build_mock_response(status_code, json_body, link)
    return AsyncMock(return_value=mock_resp)


# ── PR details: successful fetch ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_pr_details_success(service: GitHubService, mock_pr_response: dict[str, Any]):
    """A 200 response should return the expected normalised dict."""
    mock_req = _mock_client_request(200, mock_pr_response)

    with patch.object(httpx.AsyncClient, "request", mock_req):
        result = await service.get_pr_details("owner", "repo", 1)

    assert result["owner"] == "owner"
    assert result["repo"] == "repo"
    assert result["pull_number"] == 1
    assert result["title"] == "Add login feature"
    assert result["body"] == "Implements OAuth-based login."
    assert result["author"] == "alice"
    assert result["state"] == "open"
    assert result["base_branch"] == "main"
    assert result["head_branch"] == "feature/login"
    assert result["changed_files"] == 5
    assert result["additions"] == 120
    assert result["deletions"] == 30
    assert result["html_url"] == "https://github.com/owner/repo/pull/1"
    assert "created_at" in result
    assert "updated_at" in result


# ── Error handling — PR details ───────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "json_body", "expected_exception", "expected_match"),
    [
        (401, {"message": "Bad credentials"}, AuthenticationError, "authentication"),
        (403, {"message": "Resource not accessible by integration"}, PermissionDeniedError, "Access denied"),
        (404, {"message": "Not Found"}, NotFoundError, "not found"),
        (429, {"message": "API rate limit exceeded"}, RateLimitError, "rate limit"),
        (500, {"message": "Internal Server Error"}, GitHubServiceError, "500"),
    ],
)
async def test_error_responses(
    service: GitHubService,
    status: int,
    json_body: dict[str, Any],
    expected_exception: type[GitHubServiceError],
    expected_match: str,
):
    """Each HTTP error status should map to the correct exception."""
    mock_req = _mock_client_request(status, json_body)

    with patch.object(httpx.AsyncClient, "request", mock_req):
        with pytest.raises(expected_exception, match=expected_match):
            await service.get_pr_details("owner", "repo", 1)


@pytest.mark.asyncio
async def test_rate_limit_via_403_with_body(service: GitHubService):
    """GitHub sometimes returns 403 with 'rate limit' in the body."""
    json_body = {"message": "API rate limit exceeded (retry later)"}
    mock_req = _mock_client_request(403, json_body)
    mock_req.return_value.headers["X-RateLimit-Remaining"] = "0"

    with patch.object(httpx.AsyncClient, "request", mock_req):
        with pytest.raises(RateLimitError, match="rate limit"):
            await service.get_pr_details("owner", "repo", 1)


# ── Token loading from settings ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_token_loaded_from_settings():
    """When GitHubService() is created without a token, it should load from settings."""
    mock_req = _mock_client_request(200, {"title": "test"})
    mock_settings = AsyncMock()
    mock_settings.GITHUB_TOKEN = SecretStr("ghp_settings_token")

    with (
        patch("app.services.github_service.get_settings", return_value=mock_settings),
        patch.object(httpx.AsyncClient, "request", mock_req),
    ):
        svc = GitHubService()
        await svc.get_pr_details("owner", "repo", 1)

    call_kwargs = mock_req.call_args
    assert call_kwargs is not None, "Expected client.request() to be called"
    await svc.close()


# ── Network error handling ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_timeout_error(service: GitHubService):
    """Network timeouts should be wrapped in a friendly message."""
    mock_req = AsyncMock(side_effect=httpx.TimeoutException("Connection timed out"))

    with patch.object(httpx.AsyncClient, "request", mock_req):
        with pytest.raises(GitHubServiceError, match="timed out"):
            await service.get_pr_details("owner", "repo", 1)


@pytest.mark.asyncio
async def test_network_error(service: GitHubService):
    """Low-level network errors should be wrapped."""
    mock_req = AsyncMock(side_effect=httpx.NetworkError("DNS resolution failed"))

    with patch.object(httpx.AsyncClient, "request", mock_req):
        with pytest.raises(GitHubServiceError, match="Network error"):
            await service.get_pr_details("owner", "repo", 1)


# ── Context manager ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_context_manager():
    """async with GitHubService() should create and close the client."""
    mock_req = _mock_client_request(200, {"title": "test"})

    with patch.object(httpx.AsyncClient, "request", mock_req):
        async with GitHubService(token=SecretStr("ghp_test")) as svc:
            result = await svc.get_pr_details("owner", "repo", 1)
            assert result["title"] == "test"

    assert svc._client is None, "Client should be closed after context exit"


# ── PR files: successful fetch ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_pr_files_success(service: GitHubService, mock_files_response: list[dict[str, Any]]):
    """get_pr_files should return a normalised list of files."""
    mock_req = _mock_client_request(200, mock_files_response)

    with patch.object(httpx.AsyncClient, "request", mock_req):
        files = await service.get_pr_files("owner", "repo", 1)

    assert len(files) == 3
    assert files[0]["filename"] == "src/auth.py"
    assert files[0]["patch"].startswith("@@ -1,5")
    assert files[1]["filename"] == "src/utils.py"
    assert files[2]["filename"] == "assets/logo.png"
    assert files[2]["patch"] == "", "Binary files should have empty patch"


@pytest.mark.asyncio
async def test_get_pr_files_empty(service: GitHubService):
    """A PR with no changed files should return an empty list."""
    mock_req = _mock_client_request(200, [])

    with patch.object(httpx.AsyncClient, "request", mock_req):
        files = await service.get_pr_files("owner", "repo", 1)

    assert files == []


@pytest.mark.asyncio
async def test_get_pr_files_patch_preserved(service: GitHubService):
    """The full patch text should be preserved verbatim."""
    patch_text = "@@ -1,5 +1,10 @@\n-foo\n+bar\n+baz"
    file_data = [{
        "filename": "src/example.py",
        "status": "modified",
        "additions": 5, "deletions": 1, "changes": 6,
        "patch": patch_text,
        "raw_url": "", "blob_url": "",
    }]
    mock_req = _mock_client_request(200, file_data)

    with patch.object(httpx.AsyncClient, "request", mock_req):
        files = await service.get_pr_files("owner", "repo", 1)

    assert files[0]["patch"] == patch_text


# ── Pagination tests ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_pr_files_pagination(service: GitHubService):
    """When more than 100 files exist, GitHub paginates. Follow Link headers."""
    page_1 = [{"filename": f"src/file_{i}.py", "status": "modified", "additions": 1, "deletions": 0, "changes": 1, "patch": "", "raw_url": "", "blob_url": ""} for i in range(100)]
    page_2 = [{"filename": f"src/file_{i}.py", "status": "modified", "additions": 1, "deletions": 0, "changes": 1, "patch": "", "raw_url": "", "blob_url": ""} for i in range(100, 150)]

    next_url = "https://api.github.com/repos/owner/repo/pulls/1/files?per_page=100&page=2"

    mock_resp_1 = build_mock_response(200, page_1, link=f'<{next_url}>; rel="next", <...>; rel="last"')
    mock_resp_2 = build_mock_response(200, page_2)

    mock_req = AsyncMock(side_effect=[mock_resp_1, mock_resp_2])

    with patch.object(httpx.AsyncClient, "request", mock_req):
        files = await service.get_pr_files("owner", "repo", 1)

    assert len(files) == 150
    assert mock_req.call_count == 2


@pytest.mark.asyncio
async def test_get_pr_files_single_page(service: GitHubService):
    """A single page of results (no Link header) should work."""
    files_data = [{"filename": f"file_{i}.txt", "status": "added", "additions": 1, "deletions": 0, "changes": 1, "patch": "", "raw_url": "", "blob_url": ""} for i in range(5)]
    mock_req = _mock_client_request(200, files_data)

    with patch.object(httpx.AsyncClient, "request", mock_req):
        files = await service.get_pr_files("owner", "repo", 1)

    assert len(files) == 5
    assert mock_req.call_count == 1


# ── Link header parsing ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("link_header", "expected"),
    [
        ("", None),
        (None, None),
        ('<https://api.github.com/foo?page=2>; rel="next"', "https://api.github.com/foo?page=2"),
        ('<https://api.github.com/foo?page=2>; rel="next", <...>; rel="last"', "https://api.github.com/foo?page=2"),
        ('<https://api.github.com/foo?page=1>; rel="prev", <...>; rel="last"', None),
        ('<https://api.github.com/foo?page=3>; rel="last"', None),
    ],
)
def test_parse_next_link(link_header: str | None, expected: str | None):
    """_parse_next_link should correctly extract the next page URL."""
    result = GitHubService._parse_next_link(link_header)
    assert result == expected


# ── Error handling — PR files ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_pr_files_404(service: GitHubService):
    """A 404 on the files endpoint should raise NotFoundError."""
    mock_req = _mock_client_request(404, {"message": "Not Found"})

    with patch.object(httpx.AsyncClient, "request", mock_req):
        with pytest.raises(NotFoundError, match="not found"):
            await service.get_pr_files("owner", "repo", 9999)


# ── PR Comments ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_pr_comments_success(service: GitHubService):
    """get_pr_comments should return a list of comment dicts."""
    comments = [
        {"id": 1, "body": "Looks good!", "user": {"login": "alice"}},
        {"id": 2, "body": "Please fix the indentation", "user": {"login": "bob"}},
    ]
    mock_req = _mock_client_request(200, comments)

    with patch.object(httpx.AsyncClient, "request", mock_req):
        result = await service.get_pr_comments("owner", "repo", 1)

    assert len(result) == 2
    assert result[0]["id"] == 1
    assert result[1]["body"] == "Please fix the indentation"


@pytest.mark.asyncio
async def test_get_pr_comments_empty(service: GitHubService):
    """A PR with no comments should return an empty list."""
    mock_req = _mock_client_request(200, [])

    with patch.object(httpx.AsyncClient, "request", mock_req):
        result = await service.get_pr_comments("owner", "repo", 1)

    assert result == []


@pytest.mark.asyncio
async def test_create_pr_comment(service: GitHubService):
    """create_pr_comment should POST and return the new comment."""
    created = {"id": 100, "body": "Test review"}
    mock_req = _mock_client_request(201, created)

    with patch.object(httpx.AsyncClient, "post", mock_req):
        result = await service.create_pr_comment("owner", "repo", 1, "Test review")

    assert result["id"] == 100
    assert result["body"] == "Test review"


@pytest.mark.asyncio
async def test_update_pr_comment(service: GitHubService):
    """update_pr_comment should PATCH and return the updated comment."""
    updated = {"id": 42, "body": "Updated review"}
    mock_req = _mock_client_request(200, updated)

    with patch.object(httpx.AsyncClient, "patch", mock_req):
        result = await service.update_pr_comment("owner", "repo", 42, "Updated review")

    assert result["id"] == 42
    assert result["body"] == "Updated review"


# ── Upsert ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_creates_when_no_existing(service: GitHubService):
    """When no comment has the marker, upsert should create a new one."""
    # First call: GET comments (empty)
    # Second call: POST new comment
    created = {"id": 101, "body": "new review"}
    mock_get = _mock_client_request(200, [])  # no existing comments
    mock_post = _mock_client_request(201, created)

    with (
        patch.object(httpx.AsyncClient, "request", mock_get),
        patch.object(httpx.AsyncClient, "post", mock_post),
    ):
        result = await service.upsert_ai_review_comment("owner", "repo", 1, "## Review")
        assert result["id"] == 101


@pytest.mark.asyncio
async def test_upsert_updates_when_marker_found(service: GitHubService):
    """When a comment contains the marker, upsert should update it."""
    marker = service.COMMENT_MARKER
    existing_comment = {"id": 50, "body": f"{marker}\n\nold review"}
    updated = {"id": 50, "body": f"{marker}\n\nnew review"}

    mock_get = _mock_client_request(200, [existing_comment])
    mock_patch = _mock_client_request(200, updated)

    with (
        patch.object(httpx.AsyncClient, "request", mock_get),
        patch.object(httpx.AsyncClient, "patch", mock_patch),
    ):
        result = await service.upsert_ai_review_comment("owner", "repo", 1, "new review")
        assert result["id"] == 50


@pytest.mark.asyncio
async def test_upsert_ignores_other_comments(service: GitHubService):
    """Comments without the marker should be ignored; bot creates its own."""
    comments = [
        {"id": 1, "body": "Looks good", "user": {"login": "alice"}},
        {"id": 2, "body": "Need to fix this", "user": {"login": "bob"}},
    ]
    created = {"id": 3, "body": "bot review"}

    mock_get = _mock_client_request(200, comments)
    mock_post = _mock_client_request(201, created)

    with (
        patch.object(httpx.AsyncClient, "request", mock_get),
        patch.object(httpx.AsyncClient, "post", mock_post),
    ):
        result = await service.upsert_ai_review_comment("owner", "repo", 1, "## Review")
        assert result["id"] == 3
