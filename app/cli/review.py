"""
Review Command
==============
Typer application that handles the CLI interface.

This is the main user-facing command. It:
    1. Parses the PR URL into owner/repo/number
    2. Fetches the PR diff from GitHub
    3. Sends the diff to the LLM for review
    4. Prints the generated review to stdout (or posts it as a comment)

Usage:
    python -m app.main --pr-url https://github.com/owner/repo/pull/123
"""

import typer
from typing import Optional

# ── Create the Typer application instance ─────────────────────────────────────
#   - help:             short description for the app
#   - no_args_is_help=True: show help if no arguments provided
#
# We use @command() to register a single function as the CLI handler.
# When a Typer app has exactly ONE command, Typer automatically routes
# to it WITHOUT needing the command name on the command line.
# So:  python -m app.main --pr-url <url>      ✓
# NOT: python -m app.main review --pr-url ...  ✗
cli_app = typer.Typer(help="Review a GitHub pull request using AI", no_args_is_help=True)


@cli_app.command()
def main(
    pr_url: str = typer.Option(
        ...,
        "--pr-url",
        "-p",
        help="Full URL to the GitHub pull request (e.g. https://github.com/owner/repo/pull/123)",
        prompt=True,
    ),
    output_file: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Save the review to a file instead of printing to stdout",
    ),
    post_comment: bool = typer.Option(
        False,
        "--post-comment",
        help="Post the review as a comment on the PR (requires GITHUB_TOKEN with write access)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed logs during processing",
    ),
):
    """
    Run an AI-powered code review on the given pull request.

    This is the primary entry point for the agent.
    """
    # Typer's ... (ellipsis) means the option is required.
    # The prompt=True fallback asks interactively if not provided.
    #
    # Because Typer auto-routes when there is exactly ONE @command(),
    # we just run: python -m app.main --pr-url <url>

    # ── Step 1: Parse the PR URL ─────────────────────────────────────────────
    typer.echo(f"🔍 Parsing PR URL: {pr_url}")
    from app.utils.pr_url_parser import parse_github_pr_url

    try:
        pr_info = parse_github_pr_url(pr_url)
    except ValueError as exc:
        typer.echo(f"❌ {exc}", err=True)
        raise typer.Exit(code=1)

    if verbose:
        typer.echo(f"   ✓ Owner:       {pr_info.owner}")
        typer.echo(f"   ✓ Repo:        {pr_info.repo}")
        typer.echo(f"   ✓ PR Number:   {pr_info.pull_number}")
        typer.echo(f"   ✓ Dict output: {pr_info._asdict()}")
    else:
        typer.echo(f"   ✓ Parsed: {pr_info.owner}/{pr_info.repo}#{pr_info.pull_number}")

    # ── Step 2: Load configuration ──────────────────────────────────────────
    from app.config.settings import get_settings

    try:
        settings = get_settings()
    except SystemExit as exc:
        # get_settings() raises SystemExit with a friendly config-error
        # message when required env vars are missing.  Print it before
        # delegating to Typer's exit handling.
        if exc.code and isinstance(exc.code, str):
            typer.echo(exc.code, err=True)
        raise typer.Exit(code=1)

    if verbose:
        typer.echo(f"   ✓ Config loaded (model={settings.OPENCODE_MODEL})")

    msg = f"\n🔍 Starting review for {pr_info.owner}/{pr_info.repo} PR #{pr_info.pull_number}"
    if output_file:
        msg += f"\n📝 Output will be saved to: {output_file}"
    if post_comment:
        msg += "\n💬 Review will be posted as a PR comment"
    typer.echo(msg)

    # ── Step 3: Fetch PR data ──────────────────────────────────────────────
    # GitHubService uses async httpx under the hood, but Typer commands
    # are synchronous.  We bridge the gap with asyncio.run().
    import asyncio
    from app.services.github_service import GitHubService

    gh_service = GitHubService()

    try:
        pr_details = asyncio.run(
            gh_service.get_pr_details(
                owner=pr_info.owner,
                repo=pr_info.repo,
                pull_number=pr_info.pull_number,
            )
        )
    except Exception as exc:
        typer.echo(f"❌ Failed to fetch PR details: {exc}", err=True)
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

    # ── Step 4: Fetch changed files & patches ──────────────────────────────
    try:
        pr_files = asyncio.run(
            gh_service.get_pr_files(
                owner=pr_info.owner,
                repo=pr_info.repo,
                pull_number=pr_info.pull_number,
            )
        )
    except Exception as exc:
        typer.echo(f"❌ Failed to fetch PR files: {exc}", err=True)
        raise typer.Exit(code=1)

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

    # ── Step 5: Filter diff for LLM review ──────────────────────────────────
    from app.services.diff_filter_service import prepare_files_for_review

    filtered = prepare_files_for_review(
        pr_files,
        max_files=settings.MAX_FILES_TO_REVIEW,
        max_chars=settings.MAX_PATCH_CHARS,
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

    # ── Step 6: Build the structured review prompt ─────────────────────────
    from app.services.prompt_builder import build_pr_review_prompt

    review_prompt = build_pr_review_prompt(
        pr_details=pr_details,
        reviewable_files=filtered["reviewable_files"],
        skipped_files=filtered["skipped_files"],
        mode="full",
    )

    if verbose:
        # Show the prompt size without printing the full content
        typer.echo(f"   📝 Prompt built ({len(review_prompt)} chars, {len(filtered['reviewable_files'])} files)")

    # ── Step 7: Send to the LLM for review ─────────────────────────────────
    from app.services.llm_service import LlmService

    try:
        llm = LlmService()
        review_markdown = asyncio.run(llm.generate_pr_review(review_prompt))
    except Exception as exc:
        typer.echo(f"❌ LLM review failed: {exc}", err=True)
        raise typer.Exit(code=1)

    if verbose:
        typer.echo(f"\n   🤖 LLM review generated ({len(review_markdown)} chars)")
    else:
        typer.echo("   ✅ Review generated by LLM")

    # ── Step 8: Output the review ──────────────────────────────────────────
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
