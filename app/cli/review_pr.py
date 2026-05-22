"""
CLI Review Command — Standalone Entry Point
============================================
Provides a Typer-based CLI for running a local PR review.

Supports two ways to specify the PR:
    1. --url "https://github.com/owner/repo/pull/123"
    2. --owner owner --repo repo --pull-number 123

Usage:
    python -m app.main --url "https://github.com/owner/repo/pull/123"
    python -m app.main --owner octocat --repo Hello-World --pull-number 42 --mode quick
    python -m app.main -u "https://github.com/owner/repo/pull/123" -o review.md -v
"""

import typer
from typing import Optional

cli_app = typer.Typer(
    help="Run an AI-powered code review on a GitHub pull request",
    no_args_is_help=True,
)


@cli_app.command()
def review(
    url: Optional[str] = typer.Option(
        None,
        "--url",
        "-u",
        help="Full URL to the GitHub pull request (e.g. https://github.com/owner/repo/pull/123)",
    ),
    owner: Optional[str] = typer.Option(
        None,
        "--owner",
        help="GitHub repository owner or organisation",
    ),
    repo: Optional[str] = typer.Option(
        None,
        "--repo",
        help="GitHub repository name",
    ),
    pull_number: Optional[int] = typer.Option(
        None,
        "--pull-number",
        "-n",
        help="Pull request number",
    ),
    mode: Optional[str] = typer.Option(
        None,
        "--mode",
        "-m",
        help="Review mode: full, quick, security, performance, tests, architecture (default: from config or full)",
    ),
    output_file: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Save the review to this file instead of printing to stdout",
    ),
    post_comment: bool = typer.Option(
        False,
        "--post-comment",
        help="Post the review as a comment on the PR (uses GITHUB_TOKEN)",
    ),
    multi_agent: bool = typer.Option(
        False,
        "--multi-agent",
        help="Use multi-agent review (runs 5 specialist agents in parallel + 1 final)",
    ),
    fail_on_high_risk: bool = typer.Option(
        False,
        "--fail-on-high-risk",
        help="Exit with non-zero code if AI risk level is High (overrides config)",
    ),
    fail_on_request_changes: bool = typer.Option(
        False,
        "--fail-on-request-changes",
        help="Exit with non-zero code if AI recommends Request Changes (overrides config)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed progress output",
    ),
):
    """
    Run an AI-powered code review on a GitHub pull request.

    You must specify either:

    \b
    \t--url "https://github.com/owner/repo/pull/123"

    \b
    \tor\n

    \t--owner <user> --repo <name> --pull-number <num>

    The review mode controls the focus of the AI:
      \bfull:\t comprehensive review (default)
      \bquick:\t critical / high-risk issues only
      \bsecurity:\t security vulnerabilities and OWASP risks
    """
    # ── Validate and resolve input (URL vs owner/repo/number) ──────────────
    if url and not (owner or repo or pull_number is not None):
        # Option 1: parse URL
        from app.utils.pr_url_parser import parse_github_pr_url

        typer.echo(f"🔍 Parsing PR URL: {url}")
        try:
            pr_info = parse_github_pr_url(url)
        except ValueError as exc:
            typer.echo(f"❌ {exc}", err=True)
            raise typer.Exit(code=1)

        owner_val, repo_val, pr_num = pr_info.owner, pr_info.repo, pr_info.pull_number

    elif not url and owner and repo and pull_number is not None:
        # Option 2: use components directly
        owner_val, repo_val, pr_num = owner, repo, pull_number

    elif url and (owner or repo or pull_number is not None):
        # Both provided → error
        typer.echo(
            "❌ Use either --url OR (--owner, --repo, --pull-number), not both.",
            err=True,
        )
        raise typer.Exit(code=1)

    else:
        # Neither provided (or incomplete) → error
        typer.echo(
            "❌ You must specify the pull request:\n"
            "     --url \"https://github.com/owner/repo/pull/123\"\n"
            "   or\n"
            "     --owner <owner> --repo <repo> --pull-number <number>",
            err=True,
        )
        raise typer.Exit(code=1)

    if verbose:
        typer.echo(f"   ✓ Owner:       {owner_val}")
        typer.echo(f"   ✓ Repo:        {repo_val}")
        typer.echo(f"   ✓ PR Number:   {pr_num}")
    else:
        typer.echo(f"   ✓ Parsed: {owner_val}/{repo_val}#{pr_num}")

    # ── Load configuration ─────────────────────────────────────────────────
    from app.config.settings import get_settings

    try:
        settings = get_settings()
    except SystemExit as exc:
        if exc.code and isinstance(exc.code, str):
            typer.echo(exc.code, err=True)
        raise typer.Exit(code=1)

    if verbose:
        typer.echo(f"   ✓ Config loaded (model={settings.OPENCODE_MODEL})")

    # ── Load repository-level .ai-review.yml ───────────────────────────────
    from app.config.review_config import load_review_config

    config = load_review_config()

    # Resolve effective mode: CLI > config > default
    effective_mode: str = mode if mode is not None else config.mode
    valid_modes = ("full", "quick", "security", "performance", "tests", "architecture")
    if effective_mode not in valid_modes:
        typer.echo(f"❌ Invalid mode '{effective_mode}'. Choose one: {', '.join(valid_modes)}", err=True)
        raise typer.Exit(code=1)

    if verbose:
        typer.echo(f"   ✓ Mode:        {effective_mode}")
        if config.focus:
            typer.echo(f"   ✓ Focus areas: {', '.join(config.focus)}")
        if config.ignore:
            typer.echo(f"   ✓ Ignore patterns: {len(config.ignore)} custom")
        if effective_mode != (mode or config.mode):
            typer.echo(f"   ✓ Config file: .ai-review.yml loaded")

    msg = f"\n🔍 Starting review for {owner_val}/{repo_val} PR #{pr_num} (mode: {effective_mode})"
    if output_file:
        msg += f"\n📝 Output will be saved to: {output_file}"
    typer.echo(msg)

    # ── Run the entire async pipeline in a single event loop ──────────────
    # Multiple asyncio.run() calls would fail because httpx clients are
    # bound to a specific event loop.  Use one async function, one call.
    import asyncio
    from app.services.github_service import GitHubService

    async def _pipeline():
        gh = GitHubService()
        pd = await gh.get_pr_details(owner=owner_val, repo=repo_val, pull_number=pr_num)
        pf = await gh.get_pr_files(owner=owner_val, repo=repo_val, pull_number=pr_num)
        return pd, pf

    try:
        pr_details, pr_files = asyncio.run(_pipeline())
    except Exception as exc:
        typer.echo(f"❌ Failed to fetch PR data: {exc}", err=True)
        raise typer.Exit(code=1)

    if verbose:
        typer.echo(f"   ✓ Title:        {pr_details['title']}")
        typer.echo(f"   ✓ Author:       {pr_details['author']}")
        typer.echo(f"   ✓ State:        {pr_details['state']}")
        typer.echo(f"   ✓ Base branch:  {pr_details['base_branch']}")
        typer.echo(f"   ✓ Head branch:  {pr_details['head_branch']}")
        typer.echo(f"   ✓ Changed files:{pr_details['changed_files']}")
        typer.echo(f"   ✓ Additions:    +{pr_details['additions']}")
        typer.echo(f"   ✓ Deletions:    -{pr_details['deletions']}")
    else:
        typer.echo(f"   ✓ PR: \"{pr_details['title']}\" by @{pr_details['author']} "
                    f"({pr_details['state']}, ±{pr_details['changed_files']} files)")

    if verbose:
        typer.echo(f"\n   📄 Changed files ({len(pr_files)} total):")
        for f in pr_files:
            binary_flag = " [binary]" if not f["patch"] else ""
            typer.echo(f"       {f['status']:>8}  {f['filename']}  "
                        f"(+{f['additions']}/-{f['deletions']}){binary_flag}")
    else:
        non_binary = sum(1 for f in pr_files if f["patch"])
        binary = len(pr_files) - non_binary
        typer.echo(f"   ✓ Files: {len(pr_files)} changed "
                    f"({non_binary} with patches, {binary} binary)")

    # ── Filter diff for LLM review ──────────────────────────────────────────
    from app.services.diff_filter_service import prepare_files_for_review

    filtered = prepare_files_for_review(
        pr_files,
        max_files=config.max_files,
        max_chars=config.max_patch_chars,
        custom_ignore=config.ignore or None,
    )

    if verbose:
        typer.echo(f"\n   📊 Filtering {filtered['total_files']} files:")
        typer.echo(f"       ✅ {filtered['reviewed_files']} reviewable")
        if filtered["skipped_count"]:
            for s in filtered["skipped_files"]:
                typer.echo(f"       ⏭️  {s['filename']}: {s['reason']}")
            truncated = [f for f in filtered["reviewable_files"] if f.get("truncated")]
            for f in truncated:
                typer.echo(f"       ✂️  {f['filename']}: truncated to {f['patch_chars']} chars")
    elif filtered["skipped_count"]:
        typer.echo(f"   ✓ Filtered: {filtered['reviewed_files']} reviewable, "
                    f"{filtered['skipped_count']} skipped")
    else:
        typer.echo(f"   ✓ Filtered: {filtered['reviewed_files']} files ready for review")

    # ── Load repo standards from .ai-review/ folder ────────────────────────
    from app.services.context_loader import load_repo_standards

    repo_standards = load_repo_standards()
    if repo_standards and verbose:
        typer.echo(f"   ✓ Repo standards: {len(repo_standards)} guideline files loaded")

    # ── Build structured review prompt ─────────────────────────────────────
    from app.services.prompt_builder import build_pr_review_prompt

    review_prompt = build_pr_review_prompt(
        pr_details=pr_details,
        reviewable_files=filtered["reviewable_files"],
        skipped_files=filtered["skipped_files"],
        mode=effective_mode,
        focus_areas=config.focus or None,
        repo_standards=repo_standards if repo_standards else None,
    )

    if verbose:
        typer.echo(f"   📝 Prompt built ({len(review_prompt)} chars, "
                    f"{len(filtered['reviewable_files'])} files, "
                    f"focus={config.focus or 'all'})")

    # ── Run the entire async pipeline (LLM + comment posting) ─────────────
    # All async work must live inside ONE asyncio.run() call because httpx
    # clients are bound to a single event loop.
    from app.services.llm_service import LlmService

    eff_multi_agent = multi_agent or config.multi_agent

    async def _llm_and_comments():
        """Run LLM review, then optionally post comments (all in one loop)."""
        llm = LlmService()

        # LLM review
        if eff_multi_agent:
            from app.services.multi_agent_pipeline import run_multi_agent_review
            md = await run_multi_agent_review(
                llm=llm, pr_details=pr_details,
                reviewable_files=filtered["reviewable_files"],
                skipped_files=filtered["skipped_files"],
                repo_standards=repo_standards if repo_standards else None,
            )
        else:
            md = await llm.generate_pr_review(review_prompt)

        # Parse results
        from app.utils.risk_parser import parse_risk_from_review
        rd = parse_risk_from_review(md)

        from app.utils.inline_parser import parse_inline_comments
        ic = parse_inline_comments(md)

        # Optional: post conversation comment
        comment_result = None
        if post_comment:
            gh = GitHubService()
            comment_result = await gh.upsert_ai_review_comment(
                owner=owner_val, repo=repo_val,
                pull_number=pr_num, review_markdown=md,
            )
            # Optional: post inline comments
            if ic:
                head_sha = pr_details.get("head_sha", "")
                try:
                    await gh.create_inline_review(
                        owner=owner_val, repo=repo_val,
                        pull_number=pr_num, commit_id=head_sha,
                        body=md, comments=ic,
                    )
                except Exception:
                    pass  # inline comments are non-blocking

        return md, rd, ic, comment_result

    try:
        review_markdown, risk_data, inline_comments, comment = asyncio.run(_llm_and_comments())
    except Exception as exc:
        typer.echo(f"❌ LLM review failed: {exc}", err=True)
        raise typer.Exit(code=1)

    if verbose:
        typer.echo(f"\n   🤖 LLM review generated ({len(review_markdown)} chars)")
        if any(risk_data.values()):
            typer.echo(f"\n   📊 Risk Summary:")
            typer.echo(f"       Score:          {risk_data.get('score', '?')}/10")
            typer.echo(f"       Risk Level:     {risk_data.get('risk_level', '?')}")
            typer.echo(f"       Recommendation: {risk_data.get('recommendation', '?')}")
    else:
        typer.echo("   ✅ Review generated by LLM")

    if comment:
        typer.echo(f"   💬 Review posted as comment: {comment.get('html_url', '#')}")
    if inline_comments:
        typer.echo(f"   💬 {len(inline_comments)} inline comments included")

    # ── Output the review ──────────────────────────────────────────────────
    if output_file:
        try:
            with open(output_file, "w") as f:
                f.write(review_markdown)
            typer.echo(f"   📝 Review saved to: {output_file}")
        except OSError as exc:
            typer.echo(f"❌ Failed to write output file: {exc}", err=True)
            raise typer.Exit(code=1)
    else:
        typer.echo("\n" + "=" * 60)
        typer.echo("🤖 AI PR Review")
        typer.echo("=" * 60)
        typer.echo(review_markdown)

    typer.echo("\n✅ Review complete!")

    # ── Workflow failure rules (checked last, after comment is posted) ──────
    eff_fail_high = fail_on_high_risk or config.fail_on_high_risk
    eff_fail_changes = fail_on_request_changes or config.fail_on_request_changes

    fail_reasons: list[str] = []
    if eff_fail_high and risk_data.get("risk_level") == "High":
        fail_reasons.append("Risk level is High and --fail-on-high-risk is enabled")
    if eff_fail_changes and risk_data.get("recommendation") == "Request Changes":
        fail_reasons.append("Recommendation is Request Changes and --fail-on-request-changes is enabled")

    if fail_reasons:
        for reason in fail_reasons:
            typer.echo(f"   ❌ CI Failure: {reason}.")
        raise typer.Exit(code=1)


# ── Allow running the module directly ────────────────────────────────────────
#   python -m app.cli.review_pr --owner ... --repo ... --pull-number ... --post-comment
if __name__ == "__main__":
    cli_app()
