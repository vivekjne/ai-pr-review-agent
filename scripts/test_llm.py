#!/usr/bin/env python3
"""
Quick test for the LLM Service
===============================
Sends a simple prompt to the LLM and prints the response.

This script requires a valid .env file with:
    - OPENCODE_API_KEY
    - OPENCODE_BASE_URL  (optional — default https://opencode.ai/zen/go/v1)
    - OPENCODE_MODEL     (optional — default deepseek-v4-flash)

Usage:
    # From the project root:
    python scripts/test_llm.py

    # Or from anywhere:
    cd /path/to/ai-pr-review-agent && python scripts/test_llm.py
"""

import asyncio
import os
import sys

# ── Ensure the project root is on sys.path ──────────────────────────────────
# This allows `import app` to work when running the script from any directory.
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


async def main():
    """Send a test prompt to the LLM and print the response."""
    from app.services.llm_service import LlmService

    print("🔌 Connecting to LLM...")
    print(f"   Using settings from .env (if present) or environment variables.\n")

    svc = LlmService()

    print("📤 Sending: \"Say hello in Markdown\"")
    print()

    try:
        response = await svc.generate_pr_review("Say hello in Markdown")
        print("📥 Response:")
        print("-" * 50)
        print(response)
        print("-" * 50)
        print("\n✅ Test completed successfully!")
    except Exception as exc:
        print(f"\n❌ Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
