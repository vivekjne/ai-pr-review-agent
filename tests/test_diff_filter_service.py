"""
Tests for Diff Filter Service
==============================
Covers all skip categories, file limits, patch truncation, and edge cases.
"""

from __future__ import annotations

from app.services.diff_filter_service import prepare_files_for_review


# ── Helper to build input file dicts ──────────────────────────────────────────


def _file(
    filename: str,
    patch: str = "diff --git a/src/a.py b/src/a.py\n@@ -1 +1,2 @@\n+print('hi')",
    status: str = "modified",
    additions: int = 1,
    deletions: int = 0,
    changes: int = 1,
) -> dict:
    return {
        "filename": filename,
        "status": status,
        "additions": additions,
        "deletions": deletions,
        "changes": changes,
        "patch": patch,
        "raw_url": f"https://github.com/owner/repo/raw/abc/{filename}",
        "blob_url": f"https://github.com/owner/repo/blob/abc/{filename}",
    }


def _empty_patch_file(filename: str) -> dict:
    """A file with no patch content (binary or empty)."""
    return _file(filename, patch="")


# ── Skip categories ──────────────────────────────────────────────────────────


def test_lock_files_skipped():
    """All known lock file patterns should be skipped."""
    files = [
        _file("package-lock.json"),
        _file("yarn.lock"),
        _file("pnpm-lock.yaml"),
        _file("poetry.lock"),
        _file("Pipfile.lock"),
        _file("Gemfile.lock"),
    ]
    result = prepare_files_for_review(files)

    assert result["reviewed_files"] == 0
    assert result["skipped_count"] == 6
    for s in result["skipped_files"]:
        assert s["reason"] == "lock file"


def test_minified_files_skipped():
    """Minified JS/CSS and source maps should be skipped."""
    files = [
        _file("bundle.min.js"),
        _file("styles.min.css"),
        _file("bundle.min.js.map"),
    ]
    result = prepare_files_for_review(files)

    assert result["reviewed_files"] == 0
    assert result["skipped_count"] == 3
    assert result["skipped_files"][0]["reason"] == "minified"
    assert result["skipped_files"][1]["reason"] == "minified"
    assert result["skipped_files"][2]["reason"] == "source map"


def test_build_artifacts_skipped():
    """Files in dist/ and build/ should be skipped."""
    files = [
        _file("dist/output.js"),
        _file("build/bundle.js"),
        _file("dist/sub/module.js"),
    ]
    result = prepare_files_for_review(files)

    assert result["reviewed_files"] == 0
    assert result["skipped_count"] == 3
    for s in result["skipped_files"]:
        assert s["reason"] == "build artifact"


def test_coverage_files_skipped():
    """Files in coverage/ should be skipped."""
    files = [
        _file("coverage/lcov.info"),
        _file("coverage/html/index.html"),
    ]
    result = prepare_files_for_review(files)

    assert result["reviewed_files"] == 0
    assert result["skipped_count"] == 2


def test_generated_files_skipped():
    """Files whose name contains 'generated' should be skipped."""
    files = [
        _file("src/generated/types.ts"),
        _file("generated_proto.go"),
        _file("src/GeneratedConfig.json"),
    ]
    result = prepare_files_for_review(files)

    assert result["reviewed_files"] == 0
    assert result["skipped_count"] == 3
    for s in result["skipped_files"]:
        assert s["reason"] == "generated"


def test_binary_files_skipped():
    """Files with empty patches should be skipped as binary."""
    files = [
        _empty_patch_file("assets/logo.png"),
        _empty_patch_file("assets/font.woff2"),
    ]
    result = prepare_files_for_review(files)

    assert result["reviewed_files"] == 0
    assert result["skipped_count"] == 2
    for s in result["skipped_files"]:
        assert s["reason"] == "binary"


# ── Normal reviewable files ──────────────────────────────────────────────────


def test_regular_source_files_included():
    """Normal source files with patches should be kept."""
    files = [
        _file("src/app.py", patch="@@ -1 +1,2 @@\n+new code"),
        _file("src/utils.ts"),
    ]
    result = prepare_files_for_review(files)

    assert result["reviewed_files"] == 2
    assert result["skipped_count"] == 0
    assert result["total_files"] == 2


def test_mixed_skip_and_review():
    """A real-world mix should split correctly."""
    files = [
        _empty_patch_file("assets/logo.png"),           # binary
        _file("poetry.lock", patch=""),                  # lock (no patch)
        _file("src/app.py"),                             # reviewable
        _file("src/utils.py"),                           # reviewable
        _file("dist/output.js"),                         # build artifact
        _file("generated_proto.py"),                     # generated
    ]
    result = prepare_files_for_review(files)

    assert result["total_files"] == 6
    assert result["reviewed_files"] == 2
    assert result["skipped_count"] == 4

    reviewed_names = [f["filename"] for f in result["reviewable_files"]]
    assert "src/app.py" in reviewed_names
    assert "src/utils.py" in reviewed_names

    skipped_reasons = {s["filename"]: s["reason"] for s in result["skipped_files"]}
    assert skipped_reasons["assets/logo.png"] == "binary"
    assert skipped_reasons["poetry.lock"] == "lock file"
    assert skipped_reasons["dist/output.js"] == "build artifact"
    assert skipped_reasons["generated_proto.py"] == "generated"


# ── Limits ────────────────────────────────────────────────────────────────────


def test_max_files_limit():
    """Files beyond max_files should be skipped as 'too large'."""
    files = [_file(f"src/file_{i}.py") for i in range(10)]
    result = prepare_files_for_review(files, max_files=3)

    assert result["reviewed_files"] == 3
    assert result["skipped_count"] == 7
    assert result["total_files"] == 10
    # The first 3 sorted files are reviewable; the rest are skipped
    for s in result["skipped_files"]:
        assert s["reason"] == "too large"


def test_max_chars_cumulative():
    """Smaller files should be prioritised; larger ones skipped when budget runs out."""
    files = [
        _file("src/small.py", patch="short"),   # 5 chars
        _file("src/huge.py", patch="x" * 500),  # 500 chars
        _file("src/tiny.py", patch="tiny"),      # 4 chars
    ]
    # Sorted: tiny(4), small(5), huge(500)
    # Budget 20: tiny(4) + small(5) = 9 ≤ 20 → included. huge(500) > 11 → skip.
    result = prepare_files_for_review(files, max_files=10, max_chars=20)

    assert result["reviewed_files"] == 2
    assert result["skipped_count"] == 1
    assert result["skipped_files"][0]["filename"] == "src/huge.py"
    assert result["skipped_files"][0]["reason"] == "too large"
    assert result["reviewable_files"][0]["filename"] == "src/tiny.py"
    assert result["reviewable_files"][1]["filename"] == "src/small.py"


def test_max_chars_skip_when_budget_exceeded():
    """When a file doesn't fit in the remaining budget, skip it entirely."""
    files = [
        _file("src/a.py", patch="aaa"),          # 3 chars
        _file("src/b.py", patch="b" * 100),      # 100 chars
    ]
    result = prepare_files_for_review(files, max_files=10, max_chars=50)

    # a.py (3) ≤ 50 → include, rem = 47
    # b.py (100) > 47 → skip
    assert result["reviewed_files"] == 1
    assert result["skipped_count"] == 1
    assert result["skipped_files"][0]["filename"] == "src/b.py"
    assert result["skipped_files"][0]["reason"] == "too large"


def test_binary_files_skipped_early():
    """Binary files (empty patch) are skipped by _skip_reason before budget phase."""
    files = [
        _empty_patch_file("assets/logo.png"),
        _file("src/app.py", patch="a" * 10),  # small enough to fit budget
        _empty_patch_file("assets/icon.svg"),
    ]
    result = prepare_files_for_review(files, max_files=10, max_chars=50)

    assert result["reviewed_files"] == 1  # only app.py
    assert result["skipped_count"] == 2   # both binary
    assert result["reviewable_files"][0]["filename"] == "src/app.py"
    assert result["reviewable_files"][0]["patch_chars"] == 10


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_empty_input():
    """An empty list should return an empty result."""
    result = prepare_files_for_review([])

    assert result["total_files"] == 0
    assert result["reviewed_files"] == 0
    assert result["skipped_count"] == 0
    assert result["reviewable_files"] == []
    assert result["skipped_files"] == []


def test_all_files_skipped():
    """When every file matches a skip pattern, nothing is reviewable."""
    files = [
        _file("package-lock.json"),
        _empty_patch_file("image.png"),
        _file("generated_code.go"),
    ]
    result = prepare_files_for_review(files)

    assert result["reviewed_files"] == 0
    assert result["skipped_count"] == 3
    assert result["reviewable_files"] == []


def test_sorting_by_patch_length():
    """Reviewable files should be sorted by patch length (ascending)."""
    files = [
        _file("src/big.py", patch="x" * 1000),
        _file("src/small.py", patch="x" * 10),
        _file("src/medium.py", patch="x" * 100),
    ]
    result = prepare_files_for_review(files, max_files=3, max_chars=2000)

    names = [f["filename"] for f in result["reviewable_files"]]
    assert names == ["src/small.py", "src/medium.py", "src/big.py"]
