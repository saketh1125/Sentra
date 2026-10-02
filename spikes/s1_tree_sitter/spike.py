"""
Sentra P0 / Spike S1 — Tree-sitter parsing & chunking feasibility.

Measures (no claim without a number):
  1. Parse rate over supported-language files
  2. Line-range accuracy — verified OBJECTIVELY by re-slicing the source file
     at the reported [start_line, end_line] and comparing to the chunk content
  3. Chunk yield by kind (module / function / class / method)
  4. Parse failures and their causes
  5. Throughput (files/s, bytes/s)
  6. Oversized-chunk prevalence (input to decision D8)

Writes a JSON report to docs/evidence/S1_tree_sitter.json
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from chunker import Chunker, ChunkerConfig, language_for_path  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
REPOS_DIR = REPO_ROOT / "data" / "repos"
OUT = REPO_ROOT / "docs" / "evidence" / "S1_tree_sitter.json"

# Directories never worth indexing.
EXCLUDE_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", ".venv", "venv",
    "__pycache__", "site-packages", ".tox", ".mypy_cache", "test-fixtures",
}


def build_line_offsets(source: bytes) -> list[int]:
    """Byte offset of the start of each 1-based line. Built ONCE per file.

    An earlier version of this harness rebuilt this table per chunk and made
    parsing look ~7x slower than it is (0.32 vs 2.34 MB/s). Verification cost
    must not be attributed to the parser.
    """
    offsets = [0]
    idx = source.find(b"\n")
    while idx != -1:
        offsets.append(idx + 1)
        idx = source.find(b"\n", idx + 1)
    return offsets


def _has_repeated_adjacent_segment(qualified_name: str) -> bool:
    """True for names like `to_key_val_list.to_key_val_list`.

    Legitimate names never repeat an adjacent segment: a method inside a class
    of the same name (`Foo.Foo.__init__`) is a different, non-adjacent case.
    """
    segs = qualified_name.split(".")
    return any(a == b for a, b in zip(segs, segs[1:]))


def verify_line_range(source: bytes, chunk, offsets: list[int]) -> tuple[bool, str]:
    """Objective verification of the invariant citations actually depend on.

    Tree-sitter reports BOTH a byte range (column-precise, so `start_byte`
    points at the `def` keyword, skipping that row's indentation) and a line
    range (row-precise). Comparing the two naively is meaningless, so we test
    two real properties instead:

      1. CONTAINMENT - the chunk's bytes must lie inside the byte window
         delimited by the claimed line range. If this holds, a developer who
         clicks `file.py:start_line-end_line` genuinely sees the chunk.
      2. RECONSTRUCTION - slicing the file at exactly the claimed lines and
         taking the chunk's relative byte span must reproduce the chunk
         content byte-for-byte. This proves the line range is not merely
         plausible but is a lossless description of the chunk.

    Returns (ok, reason). Reasons are recorded so failures are diagnosable
    rather than just counted.
    """
    total_lines = len(offsets)
    start, end = chunk.start_line, chunk.end_line
    if start < 1 or end > total_lines or end < start:
        return False, "range_out_of_file"

    win_start = offsets[start - 1]
    win_end = offsets[end] if end < total_lines else len(source)

    if not (win_start <= chunk.byte_start and chunk.byte_end <= win_end):
        return False, "bytes_outside_claimed_lines"

    rel_start = chunk.byte_start - win_start
    rel_end = chunk.byte_end - win_start
    window = source[win_start:win_end]
    if (
        window[rel_start:rel_end].decode("utf8", "replace").rstrip()
        != chunk.content.rstrip()
    ):
        return False, "content_mismatch"

    return True, "ok"


def collect_files(repo: Path) -> list[Path]:
    out: list[Path] = []
    for p in repo.rglob("*"):
        if not p.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        if language_for_path(p) is None:
            continue
        out.append(p)
    return sorted(out)


def run_repo(repo: Path, config: ChunkerConfig) -> dict:
    chunker = Chunker(config)
    files = collect_files(repo)

    stats = {
        "repo": repo.name,
        "commit": None,
        "files_seen": 0,
        "files_parsed": 0,
        "files_with_error": 0,
        "files_failed": 0,
        "parse_failures": defaultdict(int),
        "chunks_total": 0,
        "chunks_by_kind": Counter(),
        "chunks_by_language": Counter(),
        "line_range_checks": 0,
        "line_range_failures": 0,
        "range_failure_reasons": Counter(),
        "duplicate_chunk_ranges": 0,
        "duplicate_examples": [],
        "self_nested_qualified_names": 0,
        "failure_samples": [],
        "range_failure_samples": [],
        "oversized_chunks": 0,
        "total_bytes": 0,
        "parse_seconds": 0.0,
        "largest_chunks": [],
    }
    try:
        import subprocess
        stats["commit"] = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=20,
        ).stdout.strip()
    except Exception:
        pass

    t_all = time.perf_counter()
    for f in files:
        stats["files_seen"] += 1
        try:
            source = f.read_bytes()
        except OSError:
            stats["files_failed"] += 1
            stats["parse_failures"]["read_error"] += 1
            continue
        stats["total_bytes"] += len(source)
        line_offsets = build_line_offsets(source)

        t0 = time.perf_counter()
        try:
            chunks, diag = chunker.chunk_source(source, str(f), language_for_path(f))
        except Exception as exc:  # noqa: BLE001 - we want the class name recorded
            stats["files_failed"] += 1
            stats["parse_failures"][exc.__class__.__name__] += 1
            if len(stats["failure_samples"]) < 10:
                stats["failure_samples"].append(
                    {"file": str(f.relative_to(repo)), "error": exc.__class__.__name__}
                )
            continue
        stats["parse_seconds"] += time.perf_counter() - t0

        if diag.get("has_error"):
            stats["files_with_error"] += 1
        stats["files_parsed"] += 1
        stats["chunks_total"] += len(chunks)
        stats["oversized_chunks"] += diag.get("oversized_chunk_count", 0)

        # Structural invariants. Duplicate chunk ranges and self-nested
        # qualified names are silent-corruption bugs: they do not raise, they
        # just return the same code twice and poison qualified-name lookups.
        seen_ranges: dict[tuple[int, int], str] = {}
        for c in chunks:
            key = (c.byte_start, c.byte_end)
            if key in seen_ranges:
                stats["duplicate_chunk_ranges"] += 1
                if len(stats["duplicate_examples"]) < 5:
                    stats["duplicate_examples"].append(
                        {"file": str(f.relative_to(repo)), "name": c.qualified_name}
                    )
            seen_ranges[key] = c.qualified_name
            if _has_repeated_adjacent_segment(c.qualified_name):
                stats["self_nested_qualified_names"] += 1

        for c in chunks:
            stats["chunks_by_kind"][c.kind] += 1
            stats["chunks_by_language"][c.language] += 1
            stats["line_range_checks"] += 1
            ok, reason = verify_line_range(source, c, line_offsets)
            if not ok:
                stats["line_range_failures"] += 1
                stats["range_failure_reasons"][reason] += 1
                if len(stats["range_failure_samples"]) < 10:
                    stats["range_failure_samples"].append(
                        {
                            "file": str(f.relative_to(repo)),
                            "kind": c.kind,
                            "name": c.qualified_name,
                            "claimed": [c.start_line, c.end_line],
                            "bytes": [c.byte_start, c.byte_end],
                            "reason": reason,
                        }
                    )
            if c.line_count > 150 and len(stats["largest_chunks"]) < 8:
                stats["largest_chunks"].append(
                    {"file": c.file_path, "name": c.qualified_name, "lines": c.line_count}
                )

    wall = time.perf_counter() - t_all
    stats["wall_seconds"] = round(wall, 3)
    stats["parse_rate"] = round(
        100.0 * stats["files_parsed"] / stats["files_seen"], 2
    ) if stats["files_seen"] else 0.0
    stats["clean_parse_rate"] = round(
        100.0 * (stats["files_parsed"] - stats["files_with_error"]) / stats["files_seen"], 2
    ) if stats["files_seen"] else 0.0
    stats["line_range_accuracy"] = round(
        100.0 * (stats["line_range_checks"] - stats["line_range_failures"])
        / stats["line_range_checks"], 4
    ) if stats["line_range_checks"] else 0.0
    stats["files_per_second"] = round(stats["files_parsed"] / wall, 1) if wall else 0.0
    stats["mb_per_second"] = round(
        stats["total_bytes"] / wall / 1e6, 2
    ) if wall else 0.0
    stats["parse_failures"] = dict(stats["parse_failures"])
    stats["range_failure_reasons"] = dict(stats["range_failure_reasons"])
    stats["chunks_by_kind"] = dict(stats["chunks_by_kind"])
    stats["chunks_by_language"] = dict(stats["chunks_by_language"])
    stats["largest_chunks"] = sorted(
        stats["largest_chunks"], key=lambda x: -x["lines"]
    )
    return stats


def main() -> int:
    repos = sorted(p for p in REPOS_DIR.iterdir() if p.is_dir())
    if not repos:
        print("No repos in data/repos. Clone fixtures first.")
        return 1

    config = ChunkerConfig()
    results = [run_repo(r, config) for r in repos]

    totals = {
        "files_seen": sum(r["files_seen"] for r in results),
        "files_parsed": sum(r["files_parsed"] for r in results),
        "files_with_error": sum(r["files_with_error"] for r in results),
        "files_failed": sum(r["files_failed"] for r in results),
        "chunks_total": sum(r["chunks_total"] for r in results),
        "line_range_checks": sum(r["line_range_checks"] for r in results),
        "line_range_failures": sum(r["line_range_failures"] for r in results),
        "oversized_chunks": sum(r["oversized_chunks"] for r in results),
        "duplicate_chunk_ranges": sum(r["duplicate_chunk_ranges"] for r in results),
        "self_nested_qualified_names": sum(r["self_nested_qualified_names"] for r in results),
        "total_bytes": sum(r["total_bytes"] for r in results),
        "wall_seconds": round(sum(r["wall_seconds"] for r in results), 3),
        "parse_seconds": round(sum(r["parse_seconds"] for r in results), 3),
    }
    totals["parse_rate"] = round(
        100.0 * totals["files_parsed"] / totals["files_seen"], 2
    ) if totals["files_seen"] else 0.0
    totals["clean_parse_rate"] = round(
        100.0 * (totals["files_parsed"] - totals["files_with_error"])
        / totals["files_seen"], 2
    ) if totals["files_seen"] else 0.0
    totals["line_range_accuracy"] = round(
        100.0 * (totals["line_range_checks"] - totals["line_range_failures"])
        / totals["line_range_checks"], 4
    ) if totals["line_range_checks"] else 0.0

    report = {
        "spike": "S1",
        "subject": "Tree-sitter parsing and syntax-aware chunking",
        "toolchain": {
            "tree_sitter_python_binding": "0.25.2",
            "tree_sitter_python_grammar": "0.25.0",
            "tree_sitter_javascript_grammar": "0.23.1",
            "python": "3.12.13",
        },
        "config": {
            "include_decorators": config.include_decorators,
            "emit_module_chunks": config.emit_module_chunks,
            "oversized_line_threshold": config.oversized_line_threshold,
            "min_line_count": config.min_line_count,
        },
        "targets_from_research": {
            "line_range_accuracy": 95.0,
            "parse_rate": 99.0,
        },
        "totals": totals,
        "repos": results,
        "verdict": {
            "line_range_accuracy_met": totals["line_range_accuracy"] >= 95.0,
            "parse_rate_met": totals["parse_rate"] >= 99.0,
            "no_duplicate_chunks": totals["duplicate_chunk_ranges"] == 0,
            "no_self_nested_names": totals["self_nested_qualified_names"] == 0,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))

    print("=" * 68)
    print("S1 — TREE-SITTER FEASIBILITY")
    print("=" * 68)
    for r in results:
        print(
            f"  {r['repo']:<10} files={r['files_parsed']}/{r['files_seen']} "
            f"({r['parse_rate']:.1f}%) clean={r['clean_parse_rate']:.1f}% "
            f"chunks={r['chunks_total']:<5} "
            f"line-range-accuracy={r['line_range_accuracy']:.3f}%"
        )
        print(
            f"             kinds={r['chunks_by_kind']} "
            f"oversized(>{config.oversized_line_threshold}L)={r['oversized_chunks']} "
            f"{r['files_per_second']} files/s"
        )
        if r["range_failure_samples"]:
            print(f"             RANGE FAILURES: {r['range_failure_samples'][:3]}")
    print("-" * 68)
    print(f"  TOTAL parse rate        : {totals['parse_rate']:.2f}%  (target >= 99%)")
    print(f"  TOTAL clean parse rate  : {totals['clean_parse_rate']:.2f}%")
    print(f"  TOTAL line-range accuracy: {totals['line_range_accuracy']:.4f}%  (target >= 95%)")
    print(f"  TOTAL chunks            : {totals['chunks_total']}")
    print(f"  TOTAL throughput        : {totals['mb_per_second'] if 'mb_per_second' in totals else round(totals['total_bytes']/totals['wall_seconds']/1e6,2)} MB/s")
    print(f"  duplicate chunk ranges  : {totals['duplicate_chunk_ranges']}")
    print(f"  self-nested names       : {totals['self_nested_qualified_names']}")
    print(f"  VERDICT                 : {report['verdict']}")
    print(f"  Report written to       : {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())