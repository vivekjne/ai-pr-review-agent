"""
GitHub REST API Client
======================
Provides methods to interact with GitHub PRs:
    - Fetch PR metadata (title, description, author, branches)
    - Fetch changed files and their diffs
    - Post and update PR review comments

All methods are async (using httpx) for performance.
"""

from pydantic import SecretStr


class GitHubClient:
    """
    Authenticated HTTP client for the GitHub REST API.

    Usage:
        client = GitHubClient(token=settings.GITHUB_TOKEN)
        pr = await client.get_pr("owner", "repo", 123)
    """

    def __init__(self, token: SecretStr):
        # TODO: Milestones 4-6
        # - Store the token
        # - Create an httpx.AsyncClient with:
        #     * base_url = "https://api.github.com"
        #     * Authorization header = "Bearer {token}"
        #     * Accept header = "application/vnd.github.v3+json"
        # - Set a reasonable timeout (e.g., 30s)
        raise NotImplementedError("To be implemented in Milestone 4")

    async def get_pr(self, owner: str, repo: str, pull_number: int) -> dict:
        """
        Fetch PR metadata from GitHub.

        GET /repos/{owner}/{repo}/pulls/{pull_number}

        Returns: PR object (title, body, head/base, user, labels, etc.)
        """
        raise NotImplementedError

    async def get_pr_files(self, owner: str, repo: str, pull_number: int) -> list[dict]:
        """
        Fetch the list of files changed in the PR, with per-file patches.

        GET /repos/{owner}/{repo}/pulls/{pull_number}/files

        Returns: list of file objects (filename, status, additions, deletions, patch)
        """
        raise NotImplementedError

    async def get_pr_diff(self, owner: str, repo: str, pull_number: int) -> str:
        """
        Fetch the full unified diff for the PR.

        GET /repos/{owner}/{repo}/pulls/{pull_number}
        Accept: application/vnd.github.v3.diff

        Returns: raw diff as a string (suitable for sending to an LLM)
        """
        raise NotImplementedError

    async def post_comment(self, owner: str, repo: str, pull_number: int, body: str) -> dict:
        """
        Post a markdown comment on the PR.

        POST /repos/{owner}/{repo}/issues/{pull_number}/comments

        Note: PR comments use the Issues API (PRs are a type of issue).
        """
        raise NotImplementedError
