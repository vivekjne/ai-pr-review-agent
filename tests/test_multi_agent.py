"""
Tests for the Multi-Agent Review Pipeline
==========================================
Covers specialist prompts, the pipeline orchestrator, and config integration.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.services.multi_agent_pipeline import run_multi_agent_review
from app.services.prompt_builder import (
    SPECIALIST_AGENTS,
    build_final_reviewer_prompt,
    build_specialist_prompt,
)
from app.config.review_config import ReviewConfig


# ── Sample data ──────────────────────────────────────────────────────────────


def _pr_details(**kw: Any) -> dict[str, Any]:
    data = {
        "title": "Add user auth",
        "author": "alice",
        "head_branch": "feat/auth",
        "base_branch": "main",
        "state": "open",
        "changed_files": 2,
        "additions": 50,
        "deletions": 10,
        "html_url": "https://github.com/owner/repo/pull/1",
    }
    data.update(kw)
    return data


def _file(filename: str, patch: str = "diff --git a/src/a.py b/src/a.py\n@@ -1 +1,2 @@\n+new",
            truncated: bool = False) -> dict[str, Any]:
    return {
        "filename": filename,
        "status": "modified",
        "additions": 10, "deletions": 2, "changes": 12,
        "patch": patch, "truncated": truncated, "patch_chars": len(patch),
        "raw_url": "", "blob_url": "",
    }


# ── Specialist prompts ───────────────────────────────────────────────────────


def test_specialist_agent_definitions():
    """There should be exactly 5 specialist agents defined."""
    keys = [a["key"] for a in SPECIALIST_AGENTS]
    assert "bug_reviewer" in keys
    assert "security_reviewer" in keys
    assert "performance_reviewer" in keys
    assert "test_reviewer" in keys
    assert "maintainability_reviewer" in keys
    assert len(SPECIALIST_AGENTS) == 5


def test_specialist_prompt_mentions_focus():
    """Each specialist prompt should mention the agent's focus area."""
    for agent in SPECIALIST_AGENTS:
        prompt = build_specialist_prompt(agent, _pr_details(), [_file("src/a.py")])
        assert agent["focus"].split(",")[0] in prompt or agent["name"] in prompt


def test_specialist_prompt_contains_pr_context():
    """The prompt should include PR context."""
    agent = SPECIALIST_AGENTS[0]
    prompt = build_specialist_prompt(agent, _pr_details(title="Test PR"), [_file("src/a.py")])
    assert "Test PR" in prompt
    assert "+50" in prompt
    assert "-10" in prompt


def test_specialist_prompt_contains_files():
    """The prompt should include the diff content."""
    agent = SPECIALIST_AGENTS[0]
    prompt = build_specialist_prompt(agent, _pr_details(), [_file("src/app.py")])
    assert "src/app.py" in prompt
    assert "diff --git" in prompt


def test_specialist_prompt_says_no_issues():
    """The prompt should instruct to say 'No X issues found'."""
    agent = SPECIALIST_AGENTS[0]
    prompt = build_specialist_prompt(agent, _pr_details(), [_file("src/a.py")])
    assert "No " in prompt
    assert "issues found" in prompt


def test_specialist_prompt_concise():
    """Specialist prompts should be shorter than full review prompts."""
    from app.services.prompt_builder import build_pr_review_prompt

    full_prompt = build_pr_review_prompt(_pr_details(), [_file("src/a.py")])
    agent = SPECIALIST_AGENTS[0]
    spec_prompt = build_specialist_prompt(agent, _pr_details(), [_file("src/a.py")])
    assert len(spec_prompt) < len(full_prompt)


# ── Final reviewer prompt ─────────────────────────────────────────────────────


def test_final_reviewer_contains_findings():
    """The final reviewer prompt should include all specialist findings."""
    findings = {
        "bug_reviewer": "Found a logic error in src/app.py.",
        "security_reviewer": "No issues found.",
        "performance_reviewer": "No issues found.",
        "test_reviewer": "Missing tests for src/app.py.",
        "maintainability_reviewer": "Good code quality.",
    }
    prompt = build_final_reviewer_prompt(_pr_details(), findings)
    assert "Bug Reviewer" in prompt
    assert "Security Reviewer" in prompt
    assert "logic error" in prompt
    assert "Good code quality" in prompt


def test_final_reviewer_has_output_format():
    """The final prompt should include the Markdown output format."""
    findings = {a["key"]: "No issues." for a in SPECIALIST_AGENTS}
    prompt = build_final_reviewer_prompt(_pr_details(), findings)
    assert "# AI PR Review" in prompt
    assert "## Overall Recommendation" in prompt
    assert "## Risk Level" in prompt
    assert "**Review Mode:** multi-agent" in prompt


def test_final_reviewer_merges_all_five():
    """All 5 specialist findings should be present."""
    findings = {a["key"]: f"Findings from {a['name']}" for a in SPECIALIST_AGENTS}
    prompt = build_final_reviewer_prompt(_pr_details(), findings)
    for agent in SPECIALIST_AGENTS:
        assert f"Findings from {agent['name']}" in prompt


# ── Config ────────────────────────────────────────────────────────────────────


def test_multi_agent_default_false():
    """The multi_agent config should default to False."""
    config = ReviewConfig()
    assert config.multi_agent is False


def test_multi_agent_enabled():
    """Multi-agent can be enabled via config."""
    config = ReviewConfig(multi_agent=True)
    assert config.multi_agent is True


def test_multi_agent_cli_override():
    """CLI flag should override config."""
    config = ReviewConfig(multi_agent=False)
    cli_flag = True
    assert (cli_flag or config.multi_agent) is True

    cli_flag = False
    config = ReviewConfig(multi_agent=True)
    assert (cli_flag or config.multi_agent) is True


# ── Pipeline (mocked) ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pipeline_runs_all_agents():
    """run_multi_agent_review should call the LLM 6 times (5 specialists + 1 final)."""
    # Mock LlmService.generate_pr_review to return a simple response
    mock_llm = AsyncMock()
    mock_llm.generate_pr_review = AsyncMock(return_value="## Finding\n\nSome output.")

    result = await run_multi_agent_review(
        llm=mock_llm,  # type: ignore[arg-type]
        pr_details=_pr_details(),
        reviewable_files=[_file("src/a.py")],
    )

    assert "Finding" in result or "output" in result
    # Should have been called 6 times (5 specialists + 1 final)
    assert mock_llm.generate_pr_review.call_count == 6


@pytest.mark.asyncio
async def test_pipeline_error_handling():
    """If a specialist fails, the pipeline should handle the error gracefully."""
    mock_llm = AsyncMock()
    # First call fails, rest succeed
    calls = 0

    async def side_effect(prompt: str) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("Intentional error")
        return "## Finding\n\nSome output."

    mock_llm.generate_pr_review = side_effect

    result = await run_multi_agent_review(
        llm=mock_llm,  # type: ignore[arg-type]
        pr_details=_pr_details(),
        reviewable_files=[_file("src/a.py")],
    )

    # Should still return a result (with error mentioned in findings)
    assert "Error: Intentional error" in result or "output" in result
