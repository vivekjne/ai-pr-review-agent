# AI PR Review Agent 🤖

A Python tool that automatically reviews GitHub pull requests using AI
(via [OpenCode Go](https://opencode.ai) or any OpenAI-compatible API).

Works in three modes: **CLI** (one-off reviews from your terminal),
**API** (FastAPI web server for integrations), and **CI/CD** (GitHub
Action that runs automatically on every PR).

---

## Features

- **6 review modes** — Full, Quick, Security, Performance, Tests, Architecture
- **Smart diff filtering** — Skips binaries, lockfiles, minified bundles, and generated code automatically
- **Multi-agent review** — 5 specialist agents run in parallel, synthesised by a final reviewer
- **Repository standards guidance** — Place `.md` guidelines in `.ai-review/` to steer review focus
- **Risk scoring** — Extracts score/risk/recommendation from the AI output
- **Workflow failure rules** — Fail CI builds when risk exceeds a threshold
- **PR comment posting** — Creates or updates review comments with a hidden dedup marker
- **Markdown output** — Structured, severity-tagged, GitHub-flavoured Markdown
- **Config file** — `.ai-review.yml` for per-repo defaults
- **Dual input** — Specify PR by URL (`--url`) or by components (`--owner + --repo + --pull-number`)
- **Opt-in everywhere** — Never posts comments, never fails CI without explicit flags

---

## Architecture

```
                         ┌────────────────────────────┐
                         │     GitHub REST API         │
                         │  (PR metadata, files,       │
                         │   comments, diffs)          │
                         └──────────┬─────────────────┘
                                    │
                    ┌───────────────▼────────────────┐
                    │       GitHubService             │
                    │  httpx.AsyncClient wrapper      │
                    │  Auth, error mapping,           │
                    │  rate-limit handling            │
                    └───────────────┬─────────────────┘
                                    │
                    ┌───────────────▼────────────────┐
                    │      Diff Filter Service        │
                    │  Categorise files (skip reasons)│
                    │  Apply MAX_FILES, MAX_CHARS     │
                    │  Custom ignore patterns         │
                    └───────────────┬─────────────────┘
                                    │
                    ┌───────────────▼────────────────┐
                    │      Prompt Builder             │
                    │  PR context + instructions      │
                    │  + output format + diff         │
                    │  + repo standards (if any)      │
                    │  + specialist agents (multi)    │
                    └───────────────┬─────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            │                       │                       │
            ▼                       ▼                       ▼
   ┌──────────────┐      ┌──────────────────┐      ┌──────────────┐
   │  OpenCode Go  │      │ .ai-review/      │      │ .ai-review   │
   │  (LLM)       │      │ repo standards   │      │ .yml config  │
   └──────────────┘      └──────────────────┘      └──────────────┘
            │
            ▼
    ┌──────────────┐
    │ Risk Parser  │
    │  JSON block  │
    │  score/risk  │
    │  /recommend  │
    └──────────────┘
```

### Pipeline (single-agent)

```
URL or owner/repo/number
    │
    ├─ 1. Parse input
    ├─ 2. Load settings + .ai-review.yml
    ├─ 3. Fetch PR details (title, author, branches, stats)
    ├─ 4. Fetch changed files + patches
    ├─ 5. Filter files (skip binaries, lockfiles, oversized)
    ├─ 6. Load repo standards (.ai-review/*.md)
    ├─ 7. Build structured prompt
    ├─ 8. Send to LLM → Markdown review
    ├─ 9. Parse risk from JSON block
    ├─ 10. Post comment (if --post-comment)
    ├─ 11. Output / save review
    └─ 12. Fail CI (if risk exceeds threshold)
```

### Pipeline (multi-agent)

When `--multi-agent` is enabled, step 8 is replaced by:

```
    ┌─ Bug Reviewer ─┐
    ├─ Security ─────┤  asyncio.gather
    ├─ Performance ──┤  (parallel)
    ├─ Tests ────────┤
    ├─ Maintainability┤
    └───────┬────────┘
            ▼
    Final Decision Reviewer (synthesises all findings)
            │
            ▼
    Structured Markdown + JSON risk block
```

---

## Project Structure

```
ai-pr-review-agent/
├── app/
│   ├── cli/                   # Typer command-line interface
│   │   └── review_pr.py       # Main CLI entry point
│   ├── config/
│   │   ├── settings.py        # Environment variables (pydantic-settings)
│   │   └── review_config.py   # .ai-review.yml loader
│   ├── schemas/
│   │   └── review.py          # Pydantic request/response models
│   ├── services/
│   │   ├── github_service.py      # GitHub REST API client
│   │   ├── llm_service.py         # OpenAI-compatible LLM client
│   │   ├── diff_filter_service.py # File filtering & truncation
│   │   ├── prompt_builder.py      # Review prompt construction
│   │   ├── review_engine.py       # Pipeline orchestrator
│   │   ├── context_loader.py      # .ai-review/ standards loader
│   │   └── multi_agent_pipeline.py # Parallel specialist agents
│   ├── utils/
│   │   ├── pr_url_parser.py   # URL → owner/repo/number
│   │   ├── formatters.py      # Markdown formatting
│   │   ├── diff_filter.py     # (deprecated)
│   │   └── risk_parser.py     # Extract score/risk from JSON block
│   └── main.py                # Entry point (CLI + FastAPI factory)
├── .github/workflows/
│   └── ai-pr-review.yml       # GitHub Actions workflow
├── tests/                     # 158+ pytest tests
├── .ai-review.yml             # Example repo config
├── .env.example               # Environment variable template
├── requirements.txt
└── README.md
```

---

## Local Setup

### Prerequisites

- Python 3.11 or later
- A [GitHub Personal Access Token](https://github.com/settings/tokens) (classic, with `repo` scope for private repos)
- An [OpenCode Go](https://opencode.ai) API key (or any OpenAI-compatible provider)

### Install

```bash
# 1. Clone
git clone <your-repo-url> && cd ai-pr-review-agent

# 2. Create virtual environment
python3 -m venv venv

# 3. Activate
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate          # Windows

# 4. Install dependencies
pip install -r requirements.txt

# 5. Configure secrets
cp .env.example .env
# Edit .env — fill in GITHUB_TOKEN and OPENCODE_API_KEY
```

### Verify

```bash
python -m app.main --help
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_TOKEN` | Yes | — | GitHub PAT with `repo` scope |
| `OPENCODE_API_KEY` | Yes | — | OpenCode Go API key |
| `OPENCODE_BASE_URL` | No | `https://opencode.ai/zen/go/v1` | API base URL |
| `OPENCODE_MODEL` | No | `deepseek-v4-flash` | Model name |
| `MAX_FILES_TO_REVIEW` | No | `20` | Max files per review |
| `MAX_PATCH_CHARS` | No | `12000` | Max diff characters |

---

## Running CLI Mode

### By URL

```bash
# Full review, print to stdout
python -m app.main --url "https://github.com/owner/repo/pull/123"

# Save to file
python -m app.main --url "..." --output review.md

# Post as PR comment
python -m app.main --url "..." --post-comment

# Quick review, verbose output
python -m app.main -u "..." -m quick -v

# Security-focused, save to file
python -m app.main -u "..." -m security -o security-review.md
```

### By components

```bash
python -m app.main --owner octocat --repo Hello-World --pull-number 42 --post-comment
```

### Multi-agent mode

```bash
python -m app.main -u "..." --multi-agent
```

### Module-direct invocation

```bash
python -m app.cli.review_pr --owner octocat --repo Hello-World --pull-number 42 --post-comment
```

### All CLI options

| Flag | Short | Description |
|------|-------|-------------|
| `--url` | `-u` | Full PR URL |
| `--owner` | | Repo owner |
| `--repo` | | Repo name |
| `--pull-number` | `-n` | PR number |
| `--mode` | `-m` | Review mode (full, quick, security, performance, tests, architecture) |
| `--output` | `-o` | Save to file |
| `--post-comment` | | Post/update comment on PR |
| `--multi-agent` | | 5 parallel specialists + 1 final |
| `--fail-on-high-risk` | | Exit non-zero if AI risk is High |
| `--fail-on-request-changes` | | Exit non-zero if AI recommends Request Changes |
| `--verbose` | `-v` | Detailed progress |

---

## Running FastAPI Mode

```bash
# Start the server
uvicorn app.main:create_app --reload
```

### Endpoints

| Path | Method | Description |
|------|--------|-------------|
| `/health` | `GET` | Health check |
| `/api/v1/review/pr` | `POST` | Run a code review |
| `/docs` | `GET` | Swagger UI |
| `/redoc` | `GET` | ReDoc UI |

### Example request

```bash
curl -X POST http://localhost:8000/api/v1/review/pr \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/owner/repo/pull/123", "mode": "security"}'
```

### With components

```bash
curl -X POST http://localhost:8000/api/v1/review/pr \
  -H "Content-Type: application/json" \
  -d '{"owner": "octocat", "repo": "Hello-World", "pull_number": 42, "post_comment": true}'
```

### Response

```json
{
  "owner": "octocat",
  "repo": "Hello-World",
  "pull_number": 42,
  "pr_title": "Add login feature",
  "pr_url": "https://github.com/octocat/Hello-World/pull/42",
  "review_markdown": "# AI PR Review\n\n...",
  "files_reviewed": 3,
  "files_skipped": 1,
  "skipped_files": [{"filename": "package-lock.json", "reason": "lock file"}],
  "score": 7,
  "risk_level": "Medium",
  "recommendation": "Needs Manual Review",
  "comment_url": null,
  "mode": "full"
}
```

---

## Cross-Repo Usage (Reviewing Other Repos)

The built-in workflow only reviews the repo it lives in. To review PRs across
**multiple repos**, you have two options:

### Option A: Push the workflow to each repo (simplest)

Copy the workflow file into every repo you want reviewed:

```bash
mkdir -p .github/workflows
cp /path/to/ai-pr-review-agent/.github/workflows/ai-pr-review.yml .github/workflows/
```

Then add `OPENCODE_API_KEY` as a secret in each repo (Settings → Secrets and
variables → Actions). No hosting needed — each repo runs its own review on
GitHub's free runners.

### Option B: Reusable composite action (centralized)

The project includes a composite action at `action/action.yml` that other repos
can reference without copying the project:

```yaml
# .github/workflows/pr-review.yml in any repo
name: AI PR Review
on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
permissions:
  contents: read
  pull-requests: read
  issues: write
jobs:
  review:
    runs-on: ubuntu-latest
    if: github.event.pull_request.draft == false
    steps:
      - uses: vivekjne/ai-pr-review-agent@main
        with:
          opencode-api-key: ${{ secrets.OPENCODE_API_KEY }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

This checks out the agent repo, installs deps, and runs the review — all from
a single `uses:` line. Push updates to the central agent repo, and every
consuming repo picks them up automatically.

### Option C: Host the FastAPI server (most flexible)

Deploy the FastAPI server to any cloud platform (Render, Railway, Fly.io) and
create a GitHub App that sends PR webhooks to it. The server reviews any PR
from any repo the app is installed on.

## GitHub Actions Setup

### 1. Add a repository secret

| Step | Detail |
|------|--------|
| Navigate to | GitHub repo → **Settings** → **Secrets and variables** → **Actions** |
| Click | **New repository secret** |
| **Name** | `OPENCODE_API_KEY` |
| **Value** | Your OpenCode Go API key |

Optional overrides (add as additional secrets if needed):

| Secret | Default value |
|--------|---------------|
| `OPENCODE_BASE_URL` | `https://opencode.ai/zen/go/v1` |
| `OPENCODE_MODEL` | `deepseek-v4-flash` |

### 2. How it works

```
Pull request opened / new commits / reopened / draft→ready
        │
        ▼
GitHub Actions triggers ai-pr-review.yml
        │
        ├─ ⓵ Checkout code
        ├─ ⓶ Setup Python 3.11
        ├─ ⓷ pip install -r requirements.txt
        └─ ⓸ python -m app.cli.review_pr --owner ... --repo ... --pull-number ... --post-comment
                │
                ├─ Fetch PR metadata & diff
                ├─ Filter files (skip binaries, lockfiles, large diffs)
                ├─ Send diff to LLM for review
                ├─ Post/update a comment on the PR
                └─ Fail CI if risk > threshold (opt-in)
```

### 3. Trigger events

| Event | When it runs |
|-------|-------------|
| `opened` | New PR (skips drafts) |
| `synchronize` | New commits pushed |
| `reopened` | Closed PR re-opened |
| `ready_for_review` | Draft → ready |
| `workflow_dispatch` | **Manual trigger** — review an existing PR |

### 4. Review an existing PR

Existing PRs don't trigger `pull_request` events. Use **manual dispatch**:

1. Go to your repo → **Actions** tab
2. Select **AI PR Review** workflow
3. Click **Run workflow**
4. Enter the PR number
5. Click **Run**

The workflow will review that PR and post/update the comment, just like it
would for a newly opened PR.

### 4. Default workflow

The built-in workflow (`.github/workflows/ai-pr-review.yml`):

```yaml
permissions:
  contents: read
  pull-requests: read
  issues: write          # for posting comments

jobs:
  review:
    if: github.event.pull_request.draft == false
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install -r requirements.txt
      - name: Run AI PR Review
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          OPENCODE_API_KEY: ${{ secrets.OPENCODE_API_KEY }}
          OPENCODE_BASE_URL: ${{ secrets.OPENCODE_BASE_URL || 'https://opencode.ai/zen/go/v1' }}
          OPENCODE_MODEL: ${{ secrets.OPENCODE_MODEL || 'deepseek-v4-flash' }}
        run: |
          python -m app.cli.review_pr \
            --owner "${GITHUB_REPOSITORY%/*}" \
            --repo "${GITHUB_REPOSITORY#*/}" \
            --pull-number "${{ github.event.pull_request.number }}" \
            --post-comment \
            --fail-on-high-risk \
            --fail-on-request-changes
```

---

## Required GitHub Secrets

| Secret | Source | Purpose |
|--------|--------|---------|
| `GITHUB_TOKEN` | Auto-provided | Read PR, post comments |
| `OPENCODE_API_KEY` | You must add | Authenticate with OpenCode Go |
| `OPENCODE_BASE_URL` | Optional (secret or default) | API endpoint override |
| `OPENCODE_MODEL` | Optional (secret or default) | Model override |

The `GITHUB_TOKEN` is automatically provided by GitHub Actions with the
`issues: write` permission. No manual setup needed.

---

## Example `.ai-review.yml`

Place this file in the root of your repository to customise the review agent:

```yaml
# ── AI PR Review — Repository Configuration ──────────────────────────────────
# All fields are optional. Delete what you don't need.

review:
  # Multi-agent: runs 5 specialist agents in parallel (costs ~6x more tokens)
  multi_agent: false

  # Review mode: full, quick, security, performance, tests, architecture
  mode: full

  # Exit non-zero on high risk or "Request Changes" (CI use)
  fail_on_high_risk: false
  fail_on_request_changes: false

  # Max files per review
  max_files: 20

  # Max diff characters per review
  max_patch_chars: 12000

# Files to always skip (integrated with built-in skip list)
ignore:
  - "package-lock.json"
  - "pnpm-lock.yaml"
  - "yarn.lock"
  - "dist/**"
  - "build/**"
  - "*.min.js"

# Focus areas for the AI (limits attention to specific concerns)
# Options: bugs, security, performance, maintainability, tests
focus:
  - bugs
  - security
  - performance
  - maintainability
  - tests
```

---

## Review Modes

| Mode | Focus | What it skips |
|------|-------|---------------|
| `full` | All aspects: correctness, security, performance, tests, maintainability | Nothing |
| `quick` | Critical/high-risk only: bugs, security flaws, blocking issues | Style nits, formatting, non-blocking |
| `security` | OWASP Top 10, injection, auth bypass, secrets, unsafe inputs | Non-security findings |
| `performance` | N+1 queries, expensive loops, rendering, bundle size | Non-performance findings |
| `tests` | Missing tests, uncovered edge cases, risky uncovered code | Non-testing findings |
| `architecture` | Module boundaries, coupling, design patterns, scalability | Non-architecture findings |

Mode precedence: **CLI flag > `.ai-review.yml` > default (full)**

---

## Failure Rules

When `--fail-on-high-risk` or `--fail-on-request-changes` is set
(or enabled in `.ai-review.yml`), the agent extracts the risk score
and recommendation from the AI review's embedded JSON block and exits
with a non-zero code if the threshold is met.

```
✅ Review complete!
   ❌ CI Failure: Risk level is High and --fail-on-high-risk is enabled.
   ❌ CI Failure: Recommendation is Request Changes and --fail-on-request-changes is enabled.
```

**The comment is always posted before the failure check**, so the CI
dashboard always shows the review even on failed runs.

Failure precedence: **CLI flag > `.ai-review.yml` > default (false — non-blocking)**

---

## Repository Standards (`.ai-review/` folder)

Place markdown guidance files in `.ai-review/` for the AI to reference:

```
.ai-review/
├── coding-standards.md
├── security-guidelines.md
├── frontend-guidelines.md
├── backend-guidelines.md
└── testing-guidelines.md
```

When present, the agent includes them in the prompt as
**Repository Review Standards** and instructs the AI to cite which
standard a finding is based on:

> According to `testing-guidelines.md`, validation logic should include unit tests.

---

## Limitations

- **Single LLM provider** — Currently only supports OpenAI-compatible APIs (OpenCode Go). No support for Anthropic, Google, or local models yet.
- **No inline PR comments** — Reviews are posted as PR conversation comments, not individual code-line suggestions. Inline comments require the Checks API + review threads, which is a different GitHub API path.
- **No GitHub App auth** — Uses a PAT or the auto-generated Actions token. A GitHub App would provide finer-grained permissions and webhook-based triggering.
- **No vector search** — Repo standards are loaded as raw text. No embeddings or semantic search for large documentation bases.
- **Token limits** — Large PRs are truncated to fit the LLM's context window. Very large diffs may lose context.
- **Cost** — Multi-agent mode calls the LLM 6 times per review. For large repos with frequent PRs, this can add up.
- **No dashboard** — No historical review data, no trends, no per-developer metrics.
- **No notifications** — Doesn't notify Slack, Teams, or email about review results.

---

## Future Improvements

- [x] 🔄 **Multi-agent review** — 5 parallel specialist agents + 1 final synthesizer (implemented)
- [ ] 💬 **Inline PR comments** — Review feedback attached to specific code lines using GitHub's pull request review API
- [ ] 🔐 **GitHub App authentication** — Replace PAT with a GitHub App for finer-grained permissions and webhook-driven architecture
- [ ] 📚 **RAG with vector DB** — Embed repository coding standards into a vector database (Chroma, Pinecone) for semantic retrieval instead of raw file loading
- [ ] 📊 **Review dashboard** — Web UI showing review history, trends, and per-developer statistics
- [ ] 🔔 **Slack/Teams notifications** — Post review summaries to team chat channels

---

## Testing

```bash
# Run all 158+ tests
pytest tests/ -v

# Specific test suites
pytest tests/test_github_service.py -v
pytest tests/test_prompt_builder.py -v
pytest tests/test_risk_parser.py -v
pytest tests/test_multi_agent.py -v
```

---

## License

MIT
