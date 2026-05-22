"""
Review Engine
=============
Orchestrates the end-to-end review pipeline:

    1. Take a PR URL
    2. Parse it into owner/repo/number
    3. Fetch PR metadata and diff from GitHub
    4. Filter out irrelevant files and truncate large diffs
    5. Build a structured prompt for the LLM
    6. Send the prompt and get a review back
    7. Format the review as Markdown
    8. Optionally post it as a PR comment

This is where all the services come together.
"""


class ReviewEngine:
    """
    Coordinates the full review workflow.

    Each step is delegated to a dedicated service so the engine
    stays readable and each piece can be tested independently.
    """

    def __init__(self):
        # TODO: Milestones 4-9
        # - self.github = GitHubClient(token)
        # - self.llm = LlmClient(api_key, base_url, model)
        raise NotImplementedError("To be implemented in later milestones")

    async def run(self, pr_url: str) -> str:
        """
        Run the full review pipeline.

        Args:
            pr_url: Full GitHub PR URL (e.g. https://github.com/owner/repo/pull/123)

        Returns:
            Markdown-formatted review text.
        """
        # TODO: Future milestones
        # 1. Parse URL → owner, repo, pr_number
        # 2. Fetch PR metadata
        # 3. Fetch PR diff/files
        # 4. Filter diff (skip binaries, lockfiles, truncate large)
        # 5. Build review prompt
        # 6. Call LLM
        # 7. Format and return
        raise NotImplementedError
