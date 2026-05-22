"""
Multi-Agent Review Pipeline
============================
Runs multiple specialist LLM agents in parallel, then a final agent
synthesises their findings into a single structured review.

When the ``multi_agent`` setting is enabled (via config or CLI flag),
the single-agent review is replaced by this pipeline.

Cost:
    - Multi-agent: 6 LLM calls (5 specialists + 1 final)
    - Single-agent: 1 LLM call

Default is single-agent (multi_agent: false).
"""

import asyncio
from typing import Any

from app.services.llm_service import LlmService
from app.services.prompt_builder import (
    SPECIALIST_AGENTS,
    build_final_reviewer_prompt,
    build_specialist_prompt,
)


async def run_multi_agent_review(
    llm: LlmService,
    pr_details: dict[str, Any],
    reviewable_files: list[dict[str, Any]],
    skipped_files: list[dict[str, str]] | None = None,
    repo_standards: dict[str, str] | None = None,
) -> str:
    """
    Run a multi-agent PR review.

    Flow:
        1. Build specialist prompts (one per agent)
        2. Run all 5 specialists in parallel
        3. Build final reviewer prompt with all findings
        4. Run final reviewer to synthesise

    Args:
        llm:               An initialised LlmService instance.
        pr_details:        PR metadata dict.
        reviewable_files:  Filtered list of reviewable file dicts.
        skipped_files:     Optional list of skipped file dicts.
        repo_standards:    Optional dict of repo standards.

    Returns:
        Final Markdown review string (includes JSON block for risk).
    """
    # ── 1. Build specialist prompts ───────────────────────────────────────
    specialist_prompts: dict[str, str] = {}
    for agent in SPECIALIST_AGENTS:
        specialist_prompts[agent["key"]] = build_specialist_prompt(
            agent=agent,
            pr_details=pr_details,
            reviewable_files=reviewable_files,
            skipped_files=skipped_files,
            repo_standards=repo_standards,
        )

    # ── 2. Run all specialists in parallel ────────────────────────────────
    async def _run_specialist(key: str, prompt: str) -> tuple[str, str]:
        try:
            result = await llm.generate_pr_review(prompt)
            return key, result.strip()
        except Exception as exc:
            return key, f"*Error: {exc}*"

    tasks = [
        _run_specialist(key, prompt)
        for key, prompt in specialist_prompts.items()
    ]
    results = await asyncio.gather(*tasks)

    specialist_findings: dict[str, str] = dict(results)

    # ── 3. Build final reviewer prompt ────────────────────────────────────
    final_prompt = build_final_reviewer_prompt(
        pr_details=pr_details,
        specialist_findings=specialist_findings,
        reviewable_files=reviewable_files,
        skipped_files=skipped_files,
    )

    # ── 4. Run final reviewer ─────────────────────────────────────────────
    final_review = await llm.generate_pr_review(final_prompt)
    return final_review.strip()
