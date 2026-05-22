"""
PR Review Prompt Builder
========================
Constructs a structured prompt for the LLM to review a pull request.

The prompt includes:
    1. PR context (title, author, branches, statistics)
    2. Output format specification (exact Markdown structure)
    3. Rules for the AI reviewer
    4. File-by-file diff patches
    5. Skipped files summary (so the AI is aware)

Usage:
    from app.services.prompt_builder import build_pr_review_prompt

    prompt = build_pr_review_prompt(
        pr_details=pr_details,
        reviewable_files=filtered["reviewable_files"],
        skipped_files=filtered["skipped_files"],
        mode="full",
    )
    review = await llm.generate_pr_review(prompt)
"""

from typing import Any


# ── Public API ────────────────────────────────────────────────────────────────


FOCUS_LABELS: dict[str, str] = {
    "bugs": "Bugs and logic errors",
    "security": "Security vulnerabilities (OWASP Top 10, injection, auth)",
    "performance": "Performance issues and inefficiencies",
    "maintainability": "Maintainability, code quality, and readability",
    "tests": "Testing gaps and test coverage",
}


def build_pr_review_prompt(
    pr_details: dict[str, Any],
    reviewable_files: list[dict[str, Any]],
    skipped_files: list[dict[str, str]] | None = None,
    mode: str = "full",
    focus_areas: list[str] | None = None,
    repo_standards: dict[str, str] | None = None,
) -> str:
    """
    Build a comprehensive review prompt for the LLM.

    Args:
        pr_details:      PR metadata dict from GitHubService.get_pr_details().
        reviewable_files: List of file dicts from prepare_files_for_review().
        skipped_files:   Optional list of {"filename", "reason"} dicts.
        mode:            Review mode — "full", "quick", "security", "performance", "tests", or "architecture".
        focus_areas:     Optional list of focus areas from .ai-review.yml.
        repo_standards:  Optional dict of filename→content from .ai-review/ folder.

    Returns:
        A single string prompt ready to pass as the user message to the LLM.
    """
    sections: list[str] = []

    # ── 1. PR CONTEXT ──────────────────────────────────────────────────────
    sections.append(_build_pr_context(pr_details))

    # ── 1b. REPO STANDARDS (if any) ────────────────────────────────────────
    if repo_standards:
        sections.append(_build_repo_standards_section(repo_standards))

    # ── 2. REVIEW INSTRUCTIONS + OUTPUT FORMAT ─────────────────────────────
    instructions = _build_instructions(mode)
    if focus_areas:
        instructions += "\n" + _build_focus_section(focus_areas)
    sections.append(instructions)

    # ── 3. RULES ───────────────────────────────────────────────────────────
    sections.append(_build_rules(mode, reviewable_files, repo_standards))

    # ── 4. FILES TO REVIEW ────────────────────────────────────────────────
    sections.append(_build_file_patches(reviewable_files))

    # ── 5. SKIPPED FILES ──────────────────────────────────────────────────
    if skipped_files:
        sections.append(_build_skipped_files(skipped_files))

    return "\n\n".join(sections)


# ── Internal builders ─────────────────────────────────────────────────────────


def _build_pr_context(pr: dict[str, Any]) -> str:
    """Build the PR context metadata section of the prompt."""
    return (
        "# PR Context\n\n"
        f"- **Title:** {pr.get('title', 'N/A')}\n"
        f"- **Author:** @{pr.get('author', 'unknown')}\n"
        f"- **Branch:** `{pr.get('head_branch', '?')}` → `{pr.get('base_branch', '?')}`\n"
        f"- **State:** {pr.get('state', 'unknown')}\n"
        f"- **Files changed:** {pr.get('changed_files', 0)}\n"
        f"- **Additions:** +{pr.get('additions', 0)}  "
        f"**Deletions:** -{pr.get('deletions', 0)}\n"
    )


def _build_instructions(mode: str) -> str:
    """Build the output format and review instructions section."""
    mode_instruction = {
        "full": (
            "Perform a **comprehensive code review** covering all aspects:\n"
            "- Correctness, logic errors, edge cases\n"
            "- Security vulnerabilities\n"
            "- Performance concerns\n"
            "- Testing gaps\n"
            "- Maintainability and code style\n"
            "- Any other issues you notice"
        ),
        "quick": (
            "Perform a **focused code review**. Only report:\n"
            "- Critical or high-risk issues (bugs, security flaws, data loss)\n"
            "- Significant logic errors\n"
            "- Blocking issues that would prevent merge\n\n"
            "Skip minor style nits, formatting suggestions, and non-blocking "
            "improvements."
        ),
        "security": (
            "Perform a **security-focused code review**. Concentrate on:\n"
            "- Injection vulnerabilities (SQL, command, XSS)\n"
            "- Authentication and authorisation bypasses\n"
            "- Secrets or credentials exposure\n"
            "- Insecure data handling or storage\n"
            "- OWASP Top 10 risks\n\n"
            "Only mention non-security findings if they directly contribute "
            "to a security concern."
        ),
        "performance": (
            "Perform a **performance-focused code review**. Concentrate on:\n"
            "- Repeated or unnecessary API calls and database queries\n"
            "- Expensive loops or O(n²) algorithms that could be optimised\n"
            "- Frontend rendering issues, large bundle sizes, unoptimised assets\n"
            "- Missing caching, lazy loading, or pagination\n"
            "- Blocking operations that could be async or parallelised\n\n"
            "Only mention non-performance findings if they directly contribute "
            "to a performance concern."
        ),
        "tests": (
            "Perform a **testing-focused code review**. Concentrate on:\n"
            "- Missing unit or integration tests for new or changed code\n"
            "- Edge cases and error paths that are not covered\n"
            "- Risky or complex logic without test coverage\n"
            "- Test quality — meaningful assertions vs implementation details\n"
            "- Boundary conditions, null/empty handling, exception paths\n\n"
            "Only mention non-testing findings if they directly contribute "
            "to a testing concern."
        ),
        "architecture": (
            "Perform an **architecture-focused code review**. Concentrate on:\n"
            "- Module boundaries and separation of concerns\n"
            "- Coupling between components — are dependencies minimised?\n"
            "- Design patterns and anti-patterns\n"
            "- Scalability and future maintainability of the design\n"
            "- Interface design — are contracts clear and stable?\n\n"
            "Only mention non-architecture findings if they directly contribute "
            "to an architectural concern."
        ),
    }.get(mode, "Perform a comprehensive code review.")

    return (
        "# Review Instructions\n\n"
        f"{mode_instruction}\n\n"
        "# Output Format\n\n"
        "Produce your review using **exactly** this Markdown structure. "
        "Skip any section that has no findings instead of writing 'None'.\n\n"
        "```\n"
        "# AI PR Review\n\n"
        "**Review Mode:** full / quick / security / performance / tests / architecture\n\n"
        "## PR Summary\n\n"
        "## Overall Recommendation\n"
        "- Approve\n"
        "- Needs Manual Review\n"
        "- Request Changes\n\n"
        "## Risk Level\n"
        "- Low / Medium / High\n\n"
        "## Score\n"
        "1 to 10\n\n"
        "## What Changed\n\n"
        "## Key Findings\n\n"
        "## File-Level Review\n\n"
        "### filename.ext\n"
        "**Risk:** Low / Medium / High\n\n"
        "**Findings:**\n"
        "- ...\n\n"
        "**Suggestions:**\n"
        "- ...\n\n"
        "## Security Concerns\n\n"
        "## Performance Concerns\n\n"
        "## Testing Concerns\n\n"
        "## Maintainability Concerns\n\n"
        "## Skipped Files\n\n"
        "## Final Notes\n\n"
        "---\n\n"
        "**Machine-readable summary** (do not include this in the main "
        "review body — it is parsed automatically)\n\n"
        "```json\n"
        '{ "score": 7, "risk_level": "Medium", "recommendation": '
        '"Needs Manual Review" }\n'
        "```\n\n"
        "---\n\n"
        "**Inline comments** (machine-readable — only produce if you have "
        "specific line-level feedback)\n\n"
        "```json\n"
        '{\n'
        '  "inline_comments": [\n'
        '    {\n'
        '      "path": "src/auth.py",\n'
        '      "line": 45,\n'
        '      "side": "RIGHT",\n'
        '      "body": "Consider using bcrypt instead of SHA256"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "```"
    )


def _build_rules(
    mode: str,
    reviewable_files: list[dict[str, Any]],
    repo_standards: dict[str, str] | None = None,
) -> str:
    """Build the rules / guardrails section of the prompt."""
    rules: list[str] = ["# Rules\n"]

    rules.append(
        "1. **Be specific.** Cite file names and line numbers from the diff "
        "whenever possible."
    )
    rules.append(
        "2. **Do not invent code.** Only review code that is actually in the "
        "diff. Do not suggest code that doesn't exist yet unless it's directly "
        "related to a finding."
    )
    rules.append(
        "3. **Acknowledge uncertainty.** If you are unsure about something, "
        "say so explicitly (e.g. 'This may introduce...', 'Consider whether...')."
    )
    rules.append(
        "4. **Note partial diffs.** If the diff has been truncated due to "
        "size limits, state this at the top of your review."
    )
    rules.append(
        "5. **Be constructive.** Do not be overly harsh. Focus on actionable "
        "feedback that helps the author improve the PR."
    )
    rules.append(
        "6. **Skip empty sections.** If a section has no findings, omit it "
        "entirely rather than writing 'None' or 'N/A'."
    )
    rules.append(
        "7. **Include a machine-readable JSON block** at the very end of "
        "your review (after ## Final Notes). The block must contain "
        "`score` (integer 1-10), `risk_level` (Low|Medium|High), "
        "and `recommendation` (Approve|Needs Manual Review|Request Changes). "
        "Use the format shown in the Output Format section."
    )
    if repo_standards:
        rules.append(
            "8. **Reference repository standards.** When a finding is based "
            "on a document in # Repository Review Standards, cite which "
            "document it comes from (e.g. 'According to coding-standards.md, "
            "prefer PascalCase for component names.')."
        )
    rules.append(
        "9. **Optional inline comments.** If you have specific line-level "
        "feedback, include an inline_comments JSON array in the machine-readable "
        "block (see Output Format). Each entry MUST have `path` (filename), "
        "`line` (integer line number), `side` (RIGHT for new code, LEFT for "
        "deleted), and `body` (1–3 sentence suggestion). "
        "Omit the array if there are no line-level findings."
    )

    truncated = [f for f in reviewable_files if f.get("truncated")]
    if truncated:
        names = ", ".join(f["filename"] for f in truncated)
        rules.append(
            f"\n**Note:** The following file patches were truncated to fit "
            f"the review size limit and may be incomplete: {names}."
        )

    return "\n".join(rules)


def _build_file_patches(reviewable_files: list[dict[str, Any]]) -> str:
    """Build the file-by-file diff patches section."""
    if not reviewable_files:
        return "# Files to Review\n\nNo reviewable changes found."

    parts: list[str] = ["# Files to Review\n"]
    for f in reviewable_files:
        filename = f.get("filename", "?")
        status = f.get("status", "modified")
        additions = f.get("additions", 0)
        deletions = f.get("deletions", 0)
        patch = f.get("patch", "")
        truncated_flag = "[truncated]" if f.get("truncated") else ""

        header = f"### {filename} ({status}, +{additions}/-{deletions}) {truncated_flag}".strip()
        parts.append(header)

        if patch:
            parts.append(f"```diff\n{patch}\n```")
        else:
            parts.append("_(binary or empty — no diff available)_")

    return "\n\n".join(parts)


def _build_repo_standards_section(standards: dict[str, str]) -> str:
    """Build the Repository Review Standards section of the prompt."""
    lines: list[str] = [
        "# Repository Review Standards\n\n"
        "The following documents from the repository's `.ai-review/` folder "
        "define team-level conventions. Evaluate the PR against these "
        "standards and reference them in your findings when relevant.\n"
    ]
    for filename, content in standards.items():
        title = filename.replace("-", " ").replace(".md", "").title()
        lines.append(f"## {title}\n")
        lines.append(content)
        lines.append("")

    return "\n".join(lines)


def _build_focus_section(focus_areas: list[str]) -> str:
    """Build a focus-areas section for the prompt instructions."""
    lines: list[str] = [
        "\n### Focus Areas\n"
        "Pay special attention to the following aspects of the code:\n"
    ]
    for area in focus_areas:
        label = FOCUS_LABELS.get(area, area)
        lines.append(f"- {label}")
    lines.append(
        "\nOther aspects may be mentioned but the above are the priority.\n"
    )
    return "\n".join(lines)


def _build_skipped_files(skipped_files: list[dict[str, str]]) -> str:
    """Build the skipped files awareness section."""
    lines: list[str] = [
        "# Skipped Files\n",
        "The following files were not included in the review:\n",
    ]
    for s in skipped_files:
        lines.append(f"- `{s.get('filename', '?')}` — {s.get('reason', 'unknown')}")

    lines.append(
        "\n_Be aware that changes in these files may affect the overall "
        "quality of the PR. Consider reviewing them separately if relevant._"
    )
    return "\n".join(lines)


# ── Multi-agent specialist prompts ────────────────────────────────────────────

SPECIALIST_AGENTS: list[dict[str, str]] = [
    {
        "key": "bug_reviewer",
        "name": "Bug Reviewer",
        "focus": "Bugs, logic errors, edge cases, null/undefined handling, race conditions, and correctness issues",
    },
    {
        "key": "security_reviewer",
        "name": "Security Reviewer",
        "focus": "Injection vulnerabilities, authentication/authorisation, secrets exposure, unsafe inputs, and OWASP risks",
    },
    {
        "key": "performance_reviewer",
        "name": "Performance Reviewer",
        "focus": "N+1 queries, expensive loops, large bundle sizes, blocking operations, and caching issues",
    },
    {
        "key": "test_reviewer",
        "name": "Test Reviewer",
        "focus": "Missing tests, uncovered edge cases, boundary conditions, and risky logic without coverage",
    },
    {
        "key": "maintainability_reviewer",
        "name": "Maintainability Reviewer",
        "focus": "Code quality, readability, naming conventions, duplication, coupling, and design patterns",
    },
]


def build_specialist_prompt(
    agent: dict[str, str],
    pr_details: dict[str, Any],
    reviewable_files: list[dict[str, Any]],
    skipped_files: list[dict[str, str]] | None = None,
    repo_standards: dict[str, str] | None = None,
) -> str:
    """
    Build a focused, concise prompt for a single specialist agent.

    Returns a string that can be sent as a user message.
    """
    parts: list[str] = [
        f"You are a {agent['name']}. Analyse this pull request diff for "
        f"**{agent['focus']}** only.\n"
    ]

    parts.append("- Do **not** report issues outside your focus area.")
    parts.append("- Be specific: cite file names and line numbers.")
    parts.append("- If you find nothing relevant, say exactly: "
                  f"'No {agent['key'].replace('_reviewer', '').replace('_', ' ')} issues found.'")

    if repo_standards:
        parts.append(
            "- If repository standards are provided below, reference them "
            "in your findings when applicable."
        )

    parts.append("")

    # ── PR Context ──────────────────────────────────────────────────────────
    parts.append("# PR Context")
    parts.append(f"- **Title:** {pr_details.get('title', 'N/A')}")
    parts.append(f"- **Files changed:** {pr_details.get('changed_files', 0)} "
                 f"(+{pr_details.get('additions', 0)}/-{pr_details.get('deletions', 0)})")
    parts.append("")

    # ── Repo standards (if any) ─────────────────────────────────────────────
    if repo_standards:
        parts.append("# Repository Review Standards")
        for filename, content in repo_standards.items():
            title = filename.replace("-", " ").replace(".md", "").title()
            parts.append(f"## {title}")
            parts.append(content)
            parts.append("")

    # ── Files to review ─────────────────────────────────────────────────────
    if not reviewable_files:
        parts.append("# Files to Review\n\nNo reviewable changes found.")
    else:
        parts.append("# Files to Review")
        for f in reviewable_files:
            fn = f.get("filename", "?")
            st = f.get("status", "modified")
            add = f.get("additions", 0)
            sub = f.get("deletions", 0)
            patch = f.get("patch", "")
            truncated = " [truncated]" if f.get("truncated") else ""
            parts.append(f"### {fn} ({st}, +{add}/-{sub}){truncated}")
            if patch:
                parts.append(f"```diff\n{patch}\n```")
            else:
                parts.append("_(binary or empty)_")

    return "\n\n".join(parts)


def build_final_reviewer_prompt(
    pr_details: dict[str, Any],
    specialist_findings: dict[str, str],
    reviewable_files: list[dict[str, Any]] | None = None,
    skipped_files: list[dict[str, str]] | None = None,
) -> str:
    """
    Build the prompt for the Final Decision Reviewer.

    Takes the findings from all 5 specialist agents and asks the LLM
    to synthesise them into a single structured Markdown review.
    """
    sections: list[str] = []

    # ── PR Context ──────────────────────────────────────────────────────────
    sections.append(_build_pr_context(pr_details))

    # ── Specialist Findings ─────────────────────────────────────────────────
    findings_lines: list[str] = [
        "# Specialist Review Findings\n\n"
        "Below are the findings from 5 specialist reviewers. "
        "Synthesise them into a single coherent review.\n"
    ]
    for agent in SPECIALIST_AGENTS:
        key = agent["key"]
        findings_text = specialist_findings.get(key, "*No findings provided.*")
        findings_lines.append(f"## {agent['name']} Findings\n")
        findings_lines.append(findings_text)
        findings_lines.append("")

    sections.append("\n".join(findings_lines))

    # ── Output format (same as single-agent) ────────────────────────────────
    sections.append(
        "# Output Format\n\n"
        "Synthesise the specialist findings above into a **single structured "
        "Markdown review** using the format below. "
        "Do NOT include separate sections per specialist. "
        "Merge findings logically.\n\n"
        "```\n"
        "# AI PR Review\n\n"
        "**Review Mode:** multi-agent\n\n"
        "## PR Summary\n\n"
        "## Overall Recommendation\n"
        "- Approve\n"
        "- Needs Manual Review\n"
        "- Request Changes\n\n"
        "## Risk Level\n"
        "- Low / Medium / High\n\n"
        "## Score\n"
        "1 to 10\n\n"
        "## What Changed\n\n"
        "## Key Findings\n\n"
        "## File-Level Review\n\n"
        "### filename.ext\n"
        "**Risk:** Low / Medium / High\n\n"
        "**Findings:**\n"
        "- ...\n\n"
        "**Suggestions:**\n"
        "- ...\n\n"
        "## Security Concerns\n\n"
        "## Performance Concerns\n\n"
        "## Testing Concerns\n\n"
        "## Maintainability Concerns\n\n"
        "## Skipped Files\n\n"
        "## Final Notes\n\n"
        "---\n\n"
        "**Machine-readable summary**\n\n"
        "```json\n"
        '{ "score": 7, "risk_level": "Medium", "recommendation": '
        '"Needs Manual Review" }\n'
        "```\n"
    )

    # ── Skipped files awareness ────────────────────────────────────────────
    if skipped_files:
        sections.append(_build_skipped_files(skipped_files))

    return "\n\n".join(sections)
