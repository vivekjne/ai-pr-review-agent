"""
GitHub REST API Service
=======================
Authenticated HTTP client for the GitHub REST API using httpx.

Provides methods to fetch pull request metadata, files, diffs, and
to post review comments. All methods are async for performance.

Usage:
    service = GitHubService()
    pr = await service.get_pr_details("octocat", "Hello-World", 123)
    files = await service.get_pr_files("octocat", "Hello-World", 123)

Environment:
    Requires GITHUB_TOKEN to be set in .env or environment.
"""

import re
import time
from typing import Any

import httpx
from pydantic import SecretStr

from app.config.settings import get_settings


# ── Custom Exceptions ─────────────────────────────────────────────────────────
# These let callers catch specific failure modes without parsing HTTP codes.


class GitHubServiceError(Exception):
    """Base exception for all GitHub service errors."""

    def __init__(self, message: str, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message)


class AuthenticationError(GitHubServiceError):
    """Raised when the token is missing, invalid, or expired (401)."""


class PermissionDeniedError(GitHubServiceError):
    """Raised when the token lacks access to the resource (403)."""


class NotFoundError(GitHubServiceError):
    """Raised when the repo or PR does not exist (404)."""


class RateLimitError(GitHubServiceError):
    """
    Raised when the API rate limit is exhausted (429 or 403 with rate-limit body).

    Attributes:
        reset_at: Unix timestamp when the rate limit resets.
        remaining: Number of requests remaining before the limit.
    """

    def __init__(self, message: str, reset_at: int | None = None, remaining: int = 0):
        self.reset_at = reset_at
        self.remaining = remaining
        retry_after = max(0, reset_at - int(time.time())) if reset_at else None
        if retry_after:
            message = f"{message} (resets in {retry_after}s)"
        super().__init__(message, status_code=429)


# ── Regex for parsing GitHub Link headers ─────────────────────────────────────

_LINK_HEADER_RE = re.compile(r'<([^>]+)>;\s*rel="([^"]+)"')


# ── Service Class ─────────────────────────────────────────────────────────────


class GitHubService:
    """
    Authenticated HTTP client for the GitHub REST API.

    Ask this service for PR data; it handles auth, errors, and rate limits
    so the callers (CLI, API, review engine) don't have to.
    """

    # GitHub API base URL — all requests go here
    BASE_URL = "https://api.github.com"

    # HTTP client timeout (seconds) — connections and reads
    TIMEOUT = 30

    def __init__(self, token: SecretStr | None = None):
        """
        Create a GitHubService instance.

        Args:
            token: A pydantic SecretStr with the GitHub PAT.
                   If None, the token is loaded from app config/settings.
                   This makes testing easier — you can pass a mock token.
        """
        self._token = token
        self._client: httpx.AsyncClient | None = None

    # ── Public API ──────────────────────────────────────────────────────────

    async def get_pr_details(
        self,
        owner: str,
        repo: str,
        pull_number: int,
    ) -> dict[str, Any]:
        """
        Fetch pull request metadata from GitHub.

        API called: GET /repos/{owner}/{repo}/pulls/{pull_number}
        Docs: https://docs.github.com/en/rest/pulls/pulls#get-a-pull-request

        Args:
            owner:       GitHub username or organisation.
            repo:        Repository name.
            pull_number: Pull request number.

        Returns:
            Normalised dictionary with PR metadata.  Fields match the
            spec in the project requirements.

        Raises:
            AuthenticationError:  Token missing or invalid (401).
            PermissionDeniedError: Token lacks access (403).
            NotFoundError:        Repo or PR does not exist (404).
            RateLimitError:       API rate limit exceeded (429 / 403).
            GitHubServiceError:   Network or unexpected error.
        """
        data = await self._get(f"/repos/{owner}/{repo}/pulls/{pull_number}")

        return {
            "owner": owner,
            "repo": repo,
            "pull_number": pull_number,
            "title": data.get("title", ""),
            "body": data.get("body") or "",
            "author": (data.get("user") or {}).get("login", "unknown"),
            "state": data.get("state", "unknown"),
            "base_branch": (data.get("base") or {}).get("ref", ""),
            "head_branch": (data.get("head") or {}).get("ref", ""),
            "head_sha": (data.get("head") or {}).get("sha", ""),
            "created_at": data.get("created_at", ""),
            "updated_at": data.get("updated_at", ""),
            "changed_files": data.get("changed_files", 0),
            "additions": data.get("additions", 0),
            "deletions": data.get("deletions", 0),
            "html_url": data.get("html_url", ""),
        }

    async def get_pr_files(
        self,
        owner: str,
        repo: str,
        pull_number: int,
    ) -> list[dict[str, Any]]:
        """
        Fetch the list of files changed in the pull request.

        API called (paginated): GET /repos/{owner}/{repo}/pulls/{pull_number}/files
        Docs: https://docs.github.com/en/rest/pulls/pulls#list-pull-requests-files

        Handles:
            - Pagination:  follows Link headers to fetch ALL files (>100).
            - Binary files: sets patch to "" when GitHub omits it.

        Args:
            owner:       GitHub username or organisation.
            repo:        Repository name.
            pull_number: Pull request number.

        Returns:
            List of normalised file objects.  Each file has:
                filename, status, additions, deletions, changes,
                patch ("" for binary), raw_url, blob_url

        Raises:
            Same error types as get_pr_details().
        """
        path = f"/repos/{owner}/{repo}/pulls/{pull_number}/files"
        raw_files = await self._get_paginated_list(path)
        return [self._normalize_file(f) for f in raw_files]

    # ── Comment marker for upsert deduplication ──────────────────────────────
    COMMENT_MARKER = "<!-- ai-pr-review-agent -->"

    # ── Comment methods ─────────────────────────────────────────────────────

    async def get_pr_comments(
        self,
        owner: str,
        repo: str,
        pull_number: int,
    ) -> list[dict[str, Any]]:
        """
        Fetch all comments on a pull request.

        PR comments use the Issues Comments API because PRs are a
        special type of issue on GitHub.

        API: GET /repos/{owner}/{repo}/issues/{pull_number}/comments
        Docs: https://docs.github.com/en/rest/issues/comments

        Returns:
            A list of comment dicts (id, body, user, created_at, etc.).
        """
        path = f"/repos/{owner}/{repo}/issues/{pull_number}/comments"
        return await self._get_paginated_list(path)

    async def create_pr_comment(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        body: str,
    ) -> dict[str, Any]:
        """
        Create a new comment on a pull request.

        API: POST /repos/{owner}/{repo}/issues/{pull_number}/comments
        Body: {"body": "..."}
        """
        path = f"/repos/{owner}/{repo}/issues/{pull_number}/comments"
        return await self._post(path, {"body": body})

    async def update_pr_comment(
        self,
        owner: str,
        repo: str,
        comment_id: int,
        body: str,
    ) -> dict[str, Any]:
        """
        Update an existing comment on a pull request.

        API: PATCH /repos/{owner}/{repo}/issues/comments/{comment_id}
        Body: {"body": "..."}
        """
        path = f"/repos/{owner}/{repo}/issues/comments/{comment_id}"
        return await self._patch(path, {"body": body})

    async def upsert_ai_review_comment(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        review_markdown: str,
    ) -> dict[str, Any]:
        """
        Create or update the AI review comment on a PR.

        Uses a hidden HTML marker (COMMENT_MARKER) at the top of the
        comment body to detect existing bot comments.

        Flow:
            1. Prepend COMMENT_MARKER to the review text
            2. Fetch all existing PR comments
            3. Search for COMMENT_MARKER in comment bodies
            4. If found → update that comment
            5. If not found → create a new comment

        Args:
            owner:          GitHub owner.
            repo:           Repository name.
            pull_number:    Pull request number.
            review_markdown: The AI-generated Markdown review.

        Returns:
            The comment dict (from create or update response).
        """
        body = f"{self.COMMENT_MARKER}\n\n{review_markdown}"

        comments = await self.get_pr_comments(owner, repo, pull_number)

        for comment in comments:
            existing_body = comment.get("body") or ""
            if self.COMMENT_MARKER in existing_body:
                return await self.update_pr_comment(
                    owner=owner,
                    repo=repo,
                    comment_id=comment["id"],
                    body=body,
                )

        return await self.create_pr_comment(
            owner=owner,
            repo=repo,
            pull_number=pull_number,
            body=body,
        )

    async def verify_token(self) -> dict[str, Any]:
        """Test that the current token works by calling the GitHub API."""
        return await self._get("/")

    async def create_inline_review(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        commit_id: str,
        body: str,
        comments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Create a pull request review with inline comments.

        API: POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews
        Docs: https://docs.github.com/en/rest/pulls/reviews

        Args:
            owner:      GitHub owner.
            repo:       Repository name.
            pull_number: PR number.
            commit_id:  SHA of the PR's head commit (from get_pr_details).
            body:       Overall review summary Markdown.
            comments:   List of {path, line, side, body} dicts.

        Returns:
            The review dict from the GitHub API.
        """
        path = f"/repos/{owner}/{repo}/pulls/{pull_number}/reviews"
        payload: dict[str, Any] = {
            "commit_id": commit_id,
            "body": body,
            "event": "COMMENT",
            "comments": comments,
        }
        client = await self._get_client()
        try:
            response = await client.post(path, json=payload)
        except httpx.TimeoutException:
            raise GitHubServiceError(f"Request timed out: POST {path}")
        except httpx.NetworkError as exc:
            raise GitHubServiceError(f"Network error: {exc}")
        except httpx.HTTPError as exc:
            raise GitHubServiceError(f"HTTP request failed: {exc}")

        if response.is_success:
            return response.json()

        self._raise_for_status(response, "POST", path)

    # ── Internal: low-level HTTP request ────────────────────────────────────

    async def _request(self, method: str, url: str) -> httpx.Response:
        """
        Send an authenticated HTTP request and map errors to exceptions.

        This is the single choke-point for HTTP error handling, so all
        error-mapping logic lives here instead of being duplicated in
        every public method.

        Args:
            method: HTTP method ("GET", "POST", "PATCH", etc.).
            url:    Full URL or path relative to base_url.

        Returns:
            The httpx Response object (allows caller to inspect
            headers for pagination, rate limits, etc.).

        Raises:
            — same as get_pr_details() —
        """
        client = await self._get_client()

        try:
            response = await client.request(method, url)
        except httpx.TimeoutException:
            raise GitHubServiceError(
                f"Request timed out after {self.TIMEOUT}s: {method} {url}"
            )
        except httpx.NetworkError as exc:
            raise GitHubServiceError(
                f"Network error connecting to GitHub API: {exc}"
            )
        except httpx.HTTPError as exc:
            raise GitHubServiceError(f"HTTP request failed: {exc}")

        if response.is_success:
            return response

        status = response.status_code

        if status == 429 or (status == 403 and self._is_rate_limit_body(response)):
            remaining = self._parse_rate_limit_remaining(response)
            reset_at = self._parse_rate_limit_reset(response)
            raise RateLimitError(
                message=(
                    f"GitHub API rate limit exceeded "
                    f"({remaining} requests remaining)"
                ),
                reset_at=reset_at,
                remaining=remaining,
            )

        if status == 401:
            raise AuthenticationError(
                "GitHub authentication failed. "
                "Check that GITHUB_TOKEN is valid and not expired.\n"
                "  → Generate a new token at: https://github.com/settings/tokens",
                status_code=401,
            )

        if status == 403:
            raise PermissionDeniedError(
                f"Access denied to {url}. "
                f"Your token may not have permission for this repository.\n"
                f"  → Ensure your GITHUB_TOKEN has the 'repo' scope for private repos.",
                status_code=403,
            )

        if status == 404:
            raise NotFoundError(
                f"Resource not found: {method} {url}\n"
                f"  → Check that the owner, repo, and PR number are correct.\n"
                f"  → If the repo is private, ensure your token has access.",
                status_code=404,
            )

        raise GitHubServiceError(
            f"GitHub API returned status {status} for {method} {url}: "
            f"{response.text[:500]}",
            status_code=status,
        )

    async def _get(self, url: str) -> Any:
        """Send a GET request and return parsed JSON."""
        resp = await self._request("GET", url)
        return resp.json()

    async def _post(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        """Send a POST request with a JSON body and return parsed JSON."""
        client = await self._get_client()
        try:
            response = await client.post(url, json=body)
        except httpx.TimeoutException:
            raise GitHubServiceError(f"Request timed out: POST {url}")
        except httpx.NetworkError as exc:
            raise GitHubServiceError(f"Network error: {exc}")
        except httpx.HTTPError as exc:
            raise GitHubServiceError(f"HTTP request failed: {exc}")

        if response.is_success:
            return response.json()

        self._raise_for_status(response, "POST", url)

    async def _patch(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        """Send a PATCH request with a JSON body and return parsed JSON."""
        client = await self._get_client()
        try:
            response = await client.patch(url, json=body)
        except httpx.TimeoutException:
            raise GitHubServiceError(f"Request timed out: PATCH {url}")
        except httpx.NetworkError as exc:
            raise GitHubServiceError(f"Network error: {exc}")
        except httpx.HTTPError as exc:
            raise GitHubServiceError(f"HTTP request failed: {exc}")

        if response.is_success:
            return response.json()

        self._raise_for_status(response, "PATCH", url)

    def _raise_for_status(self, response: httpx.Response, method: str, url: str) -> None:
        """Map non-success HTTP status to the appropriate exception."""
        status = response.status_code
        if status == 429 or (status == 403 and self._is_rate_limit_body(response)):
            remaining = self._parse_rate_limit_remaining(response)
            reset_at = self._parse_rate_limit_reset(response)
            raise RateLimitError(
                message=f"GitHub API rate limit exceeded ({remaining} requests remaining)",
                reset_at=reset_at,
                remaining=remaining,
            )
        if status == 401:
            raise AuthenticationError("GitHub authentication failed. Check GITHUB_TOKEN.", status_code=401)
        if status == 403:
            raise PermissionDeniedError(f"Access denied to {url}. Check repo scope.", status_code=403)
        if status == 404:
            raise NotFoundError(f"Resource not found: {method} {url}", status_code=404)
        raise GitHubServiceError(f"GitHub API returned status {status}: {response.text[:500]}", status_code=status)

    async def _get_paginated_list(self, path: str) -> list[dict[str, Any]]:
        """
        Fetch a paginated list endpoint and return all items.

        GitHub's REST API paginates responses using Link headers.
        This method follows 'next' links until every page is collected.

        Args:
            path: The API path (e.g. "/repos/owner/repo/pulls/1/files").

        Returns:
            A single list containing all items from all pages.
        """
        all_items: list[dict[str, Any]] = []
        url: str | None = f"{path}?per_page=100"

        while url:
            resp = await self._request("GET", url)
            page_data = resp.json()

            # GitHub returns a list from the files endpoint.
            # If the response isn't a list, something went wrong.
            if not isinstance(page_data, list):
                raise GitHubServiceError(
                    f"Expected a list from GitHub API but got {type(page_data).__name__}: "
                    f"{str(page_data)[:200]}"
                )

            all_items.extend(page_data)

            # Parse the Link header for the next page URL.
            link_header = resp.headers.get("Link", "")
            url = self._parse_next_link(link_header)

        return all_items

    # ── File normalisation ──────────────────────────────────────────────────

    @staticmethod
    def _normalize_file(file: dict[str, Any]) -> dict[str, Any]:
        """
        Normalise a single file entry from the GitHub API.

        GitHub may omit the 'patch' field for binary files (patch = null).
        We convert that to an empty string so callers always get a string.
        """
        raw_patch = file.get("patch")
        return {
            "filename": file.get("filename", ""),
            "status": file.get("status", "unknown"),
            "additions": file.get("additions", 0),
            "deletions": file.get("deletions", 0),
            "changes": file.get("changes", 0),
            "patch": raw_patch if raw_patch is not None else "",
            "raw_url": file.get("raw_url", ""),
            "blob_url": file.get("blob_url", ""),
        }

    # ── Pagination helpers ──────────────────────────────────────────────────

    @staticmethod
    def _parse_next_link(link_header: str) -> str | None:
        """
        Parse the ``rel="next"`` URL from a GitHub Link header.

        GitHub's Link header format:
            <https://api.github.com/...?page=2>; rel="next",
            <https://api.github.com/...?page=3>; rel="last"

        Returns None when there is no next page.
        """
        if not link_header:
            return None
        for part in link_header.split(","):
            match = _LINK_HEADER_RE.match(part.strip())
            if match and match.group(2) == "next":
                return match.group(1)
        return None

    # ── Internal: client lifecycle ──────────────────────────────────────────

    async def _get_client(self) -> httpx.AsyncClient:
        """
        Get or create the httpx AsyncClient.

        The client is created lazily on first use and cached for the
        lifetime of the service.  Call ``await service.close()`` when
        done to release the connection pool.
        """
        if self._client is None:
            if self._token is None:
                settings = get_settings()
                self._token = settings.GITHUB_TOKEN

            token_value = self._token.get_secret_value()

            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "Authorization": f"Bearer {token_value}",
                    "User-Agent": "AI-PR-Review-Agent/0.1.0",
                },
                timeout=httpx.Timeout(self.TIMEOUT),
            )
        return self._client

    async def close(self) -> None:
        """
        Close the underlying HTTP client and release connections.

        Call this when you're done with the service (e.g. in a FastAPI
        lifespan handler or a CLI cleanup block).
        """
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── Context-manager support ─────────────────────────────────────────────

    async def __aenter__(self) -> "GitHubService":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    # ── Rate-limit detection helpers ────────────────────────────────────────

    @staticmethod
    def _is_rate_limit_body(response: httpx.Response) -> bool:
        """Check if a 403 response body indicates a rate-limit hit."""
        try:
            body = response.json()
            message = (body.get("message") or "").lower()
            return "rate limit" in message
        except Exception:
            return False

    @staticmethod
    def _parse_rate_limit_remaining(response: httpx.Response) -> int:
        """Read the X-RateLimit-Remaining header (defaults to 0)."""
        try:
            return int(response.headers.get("X-RateLimit-Remaining", 0))
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _parse_rate_limit_reset(response: httpx.Response) -> int | None:
        """Read the X-RateLimit-Reset header as a Unix timestamp."""
        try:
            raw = response.headers.get("X-RateLimit-Reset")
            return int(raw) if raw is not None else None
        except (ValueError, TypeError):
            return None
