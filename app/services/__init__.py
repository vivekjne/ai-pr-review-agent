"""
Service Layer
=============
Core business logic that makes the agent work.

Services in this package:
    github_service.py      → Authenticated HTTP client for the GitHub REST API
    llm_service.py         → OpenAI-compatible client for LLM code review
    review_engine.py       → Orchestrates the full pipeline: diff ⟶ LLM ⟶ review
    diff_filter_service.py → Filters and truncates PR diffs for LLM context limits
    prompt_builder.py      → Builds structured review prompts for the LLM
    context_loader.py      → Loads repo standards from .ai-review/ folder
    multi_agent_pipeline.py → Runs multiple specialist agents in parallel

Each service:
    - Is a plain Python class (or a set of functions)
    - Receives its dependencies explicitly (no global state)
    - Can be unit-tested by injecting mock clients
"""
