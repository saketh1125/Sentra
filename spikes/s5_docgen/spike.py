"""
Sentra P0 / Spike S5 — Documentation generation + cost.

Measures, with no claim beyond what is measured (Sentra_research.md §9, row S5):
   1. Cost of generating one docstring-style summary per code chunk:
      LLM calls per chunk, prompt/completion tokens per chunk, latency,
      wall seconds. This is the number that decides whether M1's doc
      generation stage is affordable, and how expensive a regeneration run
      would be (FR4: hash-triggered regeneration).
   2. Coverage   — chunks with a valid, parseable generated doc / attempted.
   3. Quality    — 30 generated docs checked with deterministic, replayable
      heuristic checks (no eyeballing), each with a pass/fail + reason.
   4. Failure modes with exact errors, so the spike is diagnosable.

Out of scope here, stated rather than hidden:
   * The §9 "graph variant" (LightRAG) cannot be run — lightrag is not
     installed and installing an unvetted dependency for one measurement is
     not justified. D4 therefore stays open; this file records that gap
     instead of implying the comparison happened.
   * "Summaries for changed chunks only" is a repo-state concern (which
     chunks changed), not a cost concern. Cost is per chunk and is what this
     spike measures; the change-selection mechanism belongs to S6/M1.

Run status (recorded honestly, not stubbed):
  * The 300-chunk run is BLOCKED by the OpenRouter free-tier daily request cap
    (50/day, `free_model_daily_requests: used=51, limit=50, remaining=0`).
    A blocked run writes S5_docgen_blocked.json and leaves prior evidence
    intact — a 0% coverage number produced by a dead credential measures the
    credential, not the task, and must not replace a real measurement.
  * The valid measurement currently in S5_docgen.json is a 10-chunk PILOT
    taken before the cap was hit. Its cost-per-chunk figures are real; its
    coverage % and sample size are one-thirtieth of the target and must not be
    read as the S5 result.

Writes docs/evidence/S5_docgen.json and docs/evidence/S5_sample_docs.json
(or docs/evidence/S5_docgen_blocked.json when the provider quota blocks the run).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # spikes root: _llm
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "s1_tree_sitter"))
import _llm  # noqa: E402
from chunker import Chunker, ChunkerConfig, language_for_path  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
REPO = REPO_ROOT / "data" / "repos" / "requests"
OUT = REPO_ROOT / "docs" / "evidence" / "S5_docgen.json"
OUT_SAMPLE = REPO_ROOT / "docs" / "evidence" / "S5_sample_docs.json"

SAMPLE_SIZE = 30  # §9 asks for a 30-doc quality sample

# Out of scope for the docgen corpus but never parsed / never documented.
EXCLUDE_DIRS = {".git", "node_modules", "vendor", "dist", "build", ".venv",
                "venv", "__pycache__", "site-packages", "test-fixtures"}

# Stated budget, so "cost within a stated budget" (§9) is checkable.
# One generation call per chunk is the design target; the 2.0 ceiling is that
# target plus the one permitted transient retry. Above 2.0 the pipeline is
# paying twice or more for the same chunk, which is a design defect.
BUDGET = {"calls_per_chunk_max": 2.0, "tokens_per_chunk_max": 6000}

SUMMARY_MIN_CHARS = 10   # below this, "summary" is not a summary
SUMMARY_MAX_CHARS = 600  # above this, it is not a *concise* summary
MAX_KEY_BEHAVIORS = 12   # guard against a runaway list from the model

REFUSAL_MARKERS = (
    "i'm sorry", "i am sorry", "i cannot", "i can't", "unable to assist",
    "as an ai", "i don't have access", "cannot assist",
)

PROMPT = """You are writing the reference documentation for a code repository.
Summarise the single code unit given below so a developer can decide whether to open it.

Respond with ONLY a JSON object (no prose, no markdown fence) with exactly these fields:
{{"summary": "<one or two sentences stating what this unit does>",
 "key_behaviors": ["<2 to 4 concrete behaviours, each a short phrase>"],
 "complexity_note": "<one sentence on complexity, edge cases or risk; or \\"straightforward\\" if there are none>"}}

--- {file_path} :: {qualified_name} (lines {start}-{end}) ---
```{language}
{content}
```"""


def chunk_id(chunk) -> str:
    """Stable identity for a chunk, used to order the deterministic sample."""
    return f"{chunk.file_path}::{chunk.qualified_name}@{chunk.start_line}"


def identifiers(chunk) -> set[str]:
    """Lower-cased identifiers appearing in the chunk (name + content tokens)."""
    import re

    tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]+", chunk.content))
    tokens.update(re.findall(r"[A-Za-z_][A-Za-z0-9_]+", chunk.qualified_name))
    return {t.lower() for t in tokens if not t.isdigit()}


def load_chunks(repo: Path) -> list:
    """All chunks of the repo, deterministic order by chunk_id.

    Every file is read once and released; nothing is retained per file.
    """
    chunker = Chunker(ChunkerConfig())
    out: list = []
    for path in sorted(p for p in repo.rglob("*") if p.is_file()):
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        if language_for_path(path) is None:
            continue
        chunks, _diag = chunker.chunk_file(path, root=repo)
        out.extend(chunks)  # file bytes are already released
    out.sort(key=chunk_id)
    return out


def sample_chunks(chunks: list, limit: int) -> list:
    """Deterministic even-stride sample of `limit` chunks.

    Not random: the corpus is sorted by chunk_id, then an evenly spaced stride
    is taken. Re-running with the same corpus and limit yields the identical
    set, which is what makes the cost table comparable across runs. A head-only
    slice would sample only the alphabetically first files.
    """
    if limit <= 0 or limit >= len(chunks):
        return list(chunks)
    if limit == 1:
        return [chunks[len(chunks) // 2]]
    stride = (len(chunks) - 1) / (limit - 1)
    return [chunks[round(i * stride)] for i in range(limit)]


def build_prompt(chunk) -> str:
    return PROMPT.format(
        file_path=chunk.file_path,
        qualified_name=chunk.qualified_name,
        start=chunk.start_line,
        end=chunk.end_line,
        language=chunk.language,
        content=chunk.content,
    )


def generate_doc(chunk) -> dict:
    """One LLM call for one chunk. Returns a per-chunk record."""
    messages = [{"role": "user", "content": build_prompt(chunk)}]
    record = {
        "chunk_id": chunk_id(chunk),
        "file_path": chunk.file_path,
        "qualified_name": chunk.qualified_name,
        "kind": chunk.kind,
        "lines": chunk.line_count,
        "prompt_tokens": None,
        "completion_tokens": None,
        "reasoning_tokens": None,
        "chars_in": None,
        "chars_out": None,
        "usage_note": None,
        "latency_s": 0.0,
        "ok": False,
        "error": None,
        "doc": None,
    }
    try:
        content, usage, latency = _llm.chat(messages=messages)
    except _llm.LLMError as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        return record

    if usage.get("chars_in") is not None:
        # cli transport: no token usage exists; licence the cost table with
        # chars and leave every token field null rather than guessing.
        record["chars_in"] = usage["chars_in"]
        record["chars_out"] = usage["chars_out"]
        record["usage_note"] = usage["note"]
    else:
        record["prompt_tokens"] = usage["prompt_tokens"]
        record["completion_tokens"] = usage["completion_tokens"]
        record["reasoning_tokens"] = usage["reasoning_tokens"]
    record["latency_s"] = round(latency, 3)

    doc, err = parse_doc(content)
    if doc is None:
        record["error"] = err
        record["raw_head"] = content[:400]
        return record
    record["doc"] = doc
    record["ok"] = True
    return record


def parse_doc(content: str) -> tuple[dict | None, str | None]:
    """Parse and validate the model's JSON document.

    Validation is strict: the doc is only "covered" if it is a JSON object with
    the three required fields and usable values. A model that answers with
    prose has not produced a document, and counting it as coverage would
    overstate M1's readiness.
    """
    text = content.strip()
    if text.startswith("```"):  # tolerate a fence despite the instruction
        text = text.strip("`").removeprefix("json").strip()
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"json_decode_error:{exc.msg}(line {exc.lineno})"

    if not isinstance(doc, dict):
        return None, "not_a_json_object"
    summary = doc.get("summary")
    behaviors = doc.get("key_behaviors")
    note = doc.get("complexity_note")
    missing = [k for k, v in (("summary", summary), ("key_behaviors", behaviors),
                              ("complexity_note", note)) if v in (None, "")]
    if missing:
        return None, f"missing_fields:{','.join(missing)}"
    if not isinstance(summary, str) or not isinstance(note, str):
        return None, "non_string_field"
    if not isinstance(behaviors, list) or not all(isinstance(b, str) for b in behaviors):
        return None, "key_behaviors_not_a_list_of_strings"
    if len(behaviors) > MAX_KEY_BEHAVIORS:
        return None, f"too_many_key_behaviors:{len(behaviors)}"
    return (
        {"summary": summary.strip(),
         "key_behaviors": [b.strip() for b in behaviors],
         "complexity_note": note.strip()},
        None,
    )


# --------------------------------------------------------------------------
# Deterministic quality checks (the 30-doc sample)
# --------------------------------------------------------------------------

def check_doc(chunk, doc: dict) -> dict:
    """Replayable heuristic checks on one generated doc.

    Deliberately NOT a model-as-judge call: the checks are deterministic so a
    later run can re-grade the same docs and get the same answer. A human
    rubric grade is a separate activity (§9 asks the *spike* to hand-rate; the
    sample file is structured so the rubric can be filled in over it).
    """
    summary = doc.get("summary") or ""
    low = summary.lower()
    checks: list[tuple[str, bool, str]] = []

    summary_ok = len(summary) >= SUMMARY_MIN_CHARS
    checks.append((
        "summary_non_empty",
        summary_ok,
        f"{len(summary)} chars" if summary_ok else f"empty or <{SUMMARY_MIN_CHARS} chars",
    ))

    details = identifiers(chunk)
    mentions = chunk.qualified_name.lower() in low or any(
        len(t) > 3 and t in low for t in details
    )
    checks.append((
        "mentions_qualified_name_or_identifier",
        mentions,
        "found in summary" if mentions else "no chunk identifier appears in summary",
    ))

    refused = any(m in low for m in REFUSAL_MARKERS)
    checks.append((
        "no_refusal",
        not refused,
        "clean" if not refused else "refusal language present",
    ))

    bounded = SUMMARY_MIN_CHARS <= len(summary) <= SUMMARY_MAX_CHARS
    checks.append((
        "summary_length_within_bounds",
        bounded,
        f"{len(summary)} chars"
        + ("" if bounded else f" (allowed {SUMMARY_MIN_CHARS}-{SUMMARY_MAX_CHARS})"),
    ))

    passed = sum(1 for _, ok, _ in checks if ok)
    return {
        "chunk_id": chunk_id(chunk),
        "file_path": chunk.file_path,
        "qualified_name": chunk.qualified_name,
        "kind": chunk.kind,
        "checks": [{"name": n, "pass": ok, "detail": d} for n, ok, d in checks],
        "checks_passed": passed,
        "checks_total": len(checks),
        "verdict": "pass" if passed == len(checks) else "fail",
        "reason": "; ".join(d for _, ok, d in checks if not ok) or "all checks passed",
        "doc": doc,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="S5 — documentation generation + cost")
    ap.add_argument("--limit-chunks", type=int, default=300,
                    help="chunks to generate docs for (default 300, §9 asks for 200-500)")
    args = ap.parse_args()

    if not REPO.is_dir():
        print(f"Missing corpus: {REPO}")
        return 1

    corpus = load_chunks(REPO)
    if not corpus:
        # Zero chunks is a harness failure, not a clean measurement (S3 §7.3).
        print(f"No chunks parsed from {REPO} — refusing to report a cost table.")
        return 1

    selected = sample_chunks(corpus, args.limit_chunks)
    print(f"corpus           : {len(corpus)} chunks from {REPO.relative_to(REPO_ROOT)}")
    print(f"sampled          : {len(selected)} chunks (deterministic stride over chunk_id)")
    print(f"model            : {_llm.default_model()}\n")

    records: list[dict] = []
    t_all = time.perf_counter()

    for i, chunk in enumerate(selected, 1):
        rec = generate_doc(chunk)
        records.append(rec)
        # The daily free-tier cap is terminal: the remaining chunks are not
        # failures of the task, they are failures of the credential. Stopping
        # here keeps `coverage` a measurement of doc generation rather than a
        # measurement of a rate limit, and avoids hammering a dead endpoint.
        if _llm.STATS["quota_exhausted"]:
            print(f"\n*** STOPPED: daily free-tier quota exhausted after {i} chunks "
                  f"(not attempted: {len(selected) - i}) ***")
            break
        flag = "ok " if rec["ok"] else "FAIL"
        err = "" if rec["ok"] else f"  <- {rec['error']}"
        if rec["chars_in"] is not None:
            size = f"in={rec['chars_in']:>6}c out={rec['chars_out']:>5}c"
        else:
            size = f"in={rec['prompt_tokens']:>5} out={rec['completion_tokens']:>4}"
        print(
            f"[{i:>3}/{len(selected)}] {flag} {rec['chunk_id']:<58} "
            f"{rec['latency_s']:>5.1f}s {size}"
            f"{err}",
            flush=True,
        )

    wall = time.perf_counter() - t_all

    ok = [r for r in records if r["ok"]]
    failed = [r for r in records if not r["ok"]]
    # The real HTTP request count, including the _llm retries. Reporting
    # len(records) would understate the cost whenever the provider flakes.
    llm_calls = _llm.STATS["http_calls"]
    attempted = len(records)

    prompt_tokens = sum(r["prompt_tokens"] or 0 for r in records if r["prompt_tokens"] is not None)
    completion_tokens = sum(r["completion_tokens"] or 0 for r in records if r["completion_tokens"] is not None)
    reasoning_tokens = sum(r["reasoning_tokens"] or 0 for r in records if r["reasoning_tokens"] is not None)
    # cli transport: tokens are simply not observable, so totals stay null and
    # cost is measured in chars; chain-of-thought split is unmeasurable too.
    using_chars = any(r["chars_in"] is not None for r in records)
    if using_chars:
        prompt_tokens = completion_tokens = reasoning_tokens = None
        chars_in_total = sum(r["chars_in"] for r in records if r["chars_in"] is not None)
        chars_out_total = sum(r["chars_out"] for r in records if r["chars_out"] is not None)
        usage_note = next(r["usage_note"] for r in records if r["usage_note"] is not None)
    else:
        chars_in_total = chars_out_total = None
        usage_note = None
    api_tokens = None if prompt_tokens is None else max(0, prompt_tokens - reasoning_tokens)

    successful_latencies = [r["latency_s"] for r in ok]
    all_latencies = [r["latency_s"] for r in records]

    coverage = round(100.0 * len(ok) / attempted, 2) if attempted else 0.0

    # Quality sample: the first SAMPLE_SIZE *successful* docs in corpus order
    # (which is already sorted by chunk_id), so the sample is reproducible
    # rather than pick-of-the-draw.
    by_id = {chunk_id(c): c for c in selected}
    docs_by_id = {r["chunk_id"]: r["doc"] for r in ok}
    graded = [check_doc(by_id[cid], docs_by_id[cid]) for cid in map(chunk_id, selected)
              if cid in docs_by_id][:SAMPLE_SIZE]

    sample_pass = sum(1 for g in graded if g["verdict"] == "pass")
    per_check_fail = {}
    for g in graded:
        for c in g["checks"]:
            if not c["pass"]:
                per_check_fail[c["name"]] = per_check_fail.get(c["name"], 0) + 1

    kind_dist = {}
    for c in selected:
        kind_dist[c.kind] = kind_dist.get(c.kind, 0) + 1

    report = {
        "spike": "S5",
        "subject": "Documentation generation + cost",
        "research_row": "Sentra_research.md §9, row S5 (cost table + coverage % + 30-doc quality sample)",
        "status": (
            "complete" if len(selected) == len(records) and not _llm.STATS["quota_exhausted"]
            else "blocked_provider_quota"
        ),
        "blocked_by_quota": _llm.STATS["quota_exhausted"],
        "chunks_not_attempted": max(0, len(selected) - len(records)),
        "toolchain": {
            "model": _llm.default_model(),
            "provider": _llm.base_url(),
            "transport": "cli" if using_chars else "http",
            "client": "spikes/_llm.py (shared, reused by S7)",
        },
        "corpus": {
            "repo": REPO.name,
            "path": str(REPO.relative_to(REPO_ROOT)),
            "commit": _repo_commit(),
            "chunks_parsed": len(corpus),
            "sampling": "sorted by chunk_id (file::qualified_name@start_line), even stride",
            "requested_limit": args.limit_chunks,
            "sampled": len(selected),
            "sample_kinds": kind_dist,
        },
        "cost_table": {
            "definition": (
                "One LLM call per chunk (single prompt: chunk content -> docstring-style "
                "JSON doc). calls/chunk is therefore by construction; the measured value "
                "confirms the pipeline did not silently retry or double-bill."
            ),
            "chunks_attempted": attempted,
            "chunks_succeeded": len(ok),
            "llm_calls": llm_calls,
            "llm_retries": _llm.STATS["transient_retries"],
            "no_usable_content_responses": _llm.STATS["no_usable_content"],
            "calls_per_chunk": round(llm_calls / attempted, 4) if attempted else 0.0,
            "wall_seconds": round(wall, 2),
            "mean_latency_s": round(sum(all_latencies) / len(all_latencies), 2) if all_latencies else 0.0,
            "mean_latency_succeeded_s": round(
                sum(successful_latencies) / len(successful_latencies), 2
            ) if successful_latencies else 0.0,
            "min_latency_s": round(min(all_latencies), 2) if all_latencies else 0.0,
            "max_latency_s": round(max(all_latencies), 2) if all_latencies else 0.0,
            "usage_note": usage_note,
            "chars_in_total": chars_in_total,
            "chars_out_total": chars_out_total,
            "chars_in_per_chunk_avg": round(chars_in_total / attempted, 1) if using_chars and attempted else None,
            "chars_out_per_chunk_avg": round(chars_out_total / attempted, 1) if using_chars and attempted else None,
            "prompt_tokens_total": prompt_tokens,
            "completion_tokens_total": completion_tokens,
            "of_which_reasoning_tokens": reasoning_tokens,
            "of_which_output_tokens": api_tokens,
            "prompt_tokens_per_chunk_avg": round(prompt_tokens / attempted, 1) if attempted and prompt_tokens is not None else None,
            "completion_tokens_per_chunk_avg": round(completion_tokens / attempted, 1) if attempted and completion_tokens is not None else None,
            "reasoning_tokens_per_chunk_avg": round(reasoning_tokens / attempted, 1) if attempted and reasoning_tokens is not None else None,
            "output_tokens_per_chunk_avg": round(api_tokens / attempted, 1) if attempted and api_tokens is not None else None,
            "chunks_per_second": round(attempted / wall, 4) if wall else 0.0,
            "projected_seconds_per_1000_chunks": round(1000 * wall / attempted, 1) if attempted else 0.0,
            "budget": BUDGET,
            "within_budget": {
                "calls_per_chunk": (llm_calls / attempted if attempted else 0.0)
                <= BUDGET["calls_per_chunk_max"],
                # tokens are not observable on the cli transport (chars only),
                # so the token budget check is null rather than guessed.
                "tokens_per_chunk": None if using_chars else
                (prompt_tokens / attempted if attempted else 0.0)
                <= BUDGET["tokens_per_chunk_max"],
            },
        },
        "coverage": {
            "definition": "chunks with a valid parsed JSON doc / chunks attempted",
            "coverage_pct": coverage,
            "success": len(ok),
            "failures": len(failed),
            "target_pct": 95.0,
            "target_met": coverage >= 95.0,
            "failure_reasons": _count_reasons(failed),
            "failures": [
                {"chunk_id": r["chunk_id"], "kind": r["kind"], "lines": r["lines"],
                 "error": r["error"], "raw_head": r.get("raw_head")}
                for r in failed
            ],
        },
        "quality_sample": {
            "definition": (
                "Deterministic heuristic checks over the first 30 successful docs in "
                "chunk_id order. Not model-as-judge: the same doc re-grades identically."
            ),
            "size": len(graded),
            "checked": len(graded),
            "passed": sample_pass,
            "pass_rate_pct": round(100.0 * sample_pass / len(graded), 2) if graded else 0.0,
            "per_check_failures": per_check_fail,
            "detail": graded,
        },
        "out_of_scope": {
            "graph_variant": (
                "§9 asks for the graph-layer variant (LightRAG) to be re-counted. "
                "NOT MEASURED: lightrag is not installed and installing an unvetted "
                "dependency for one measurement is not justified. D4 stays open."
            ),
            "changed_chunks_only": (
                "§9 phrase 'summaries for changed chunks only' is a repo-state "
                "selection concern measured by S6, not a cost concern; cost is per chunk."
            ),
            "human_rubric": (
                "The 30-doc sample here is heuristic-graded. A hand rubric grade is a "
                "human activity; the sample file is structured to be annotated over."
            ),
        },
        "verdict": {
            "coverage_met": coverage >= 95.0,
            "cost_table_produced": True,
            "quality_sample_produced": len(graded) == SAMPLE_SIZE,
            "graph_layer_cost_quantified": False,
            "budget_met": None,  # filled below
        },
    }
    ct = report["cost_table"]
    report["verdict"]["budget_met"] = all(v for v in ct["within_budget"].values() if v is not None)

    OUT.parent.mkdir(parents=True, exist_ok=True)

    # A run blocked by the provider's daily quota is NOT a measurement of doc
    # generation. Overwriting a valid earlier run would destroy real evidence
    # and replace it with a 0% coverage number that measures the credential,
    # not the task. So: keep the earlier evidence, record the block beside it.
    if report["status"] == "blocked_provider_quota":
        blocked_out = REPO_ROOT / "docs" / "evidence" / "S5_docgen_blocked.json"
        blocked_out.write_text(
            json.dumps(
                {
                    **report,
                    "note": (
                        "Run blocked by the free-tier daily request cap before any "
                        "docgen measurement could be taken. This is a credential "
                        "failure, not a result. The valid measurement remains in "
                        "S5_docgen.json."
                    ),
                    "quota_snapshot": quota_snapshot(),
                },
                indent=2,
            )
        )
        print(f"\n  Blocked-run record: {blocked_out.relative_to(REPO_ROOT)} "
              f"(prior evidence left intact)")
        return 0

    OUT.write_text(json.dumps(report, indent=2))

    if _llm.STATS["quota_exhausted"]:
        print(
            f"\n  NOT a docgen measurement: the free-tier credential hit its daily cap.\n"
            f"  Only {len(ok)}/{len(selected)} chunks were attempted. Re-run after the\n"
            f"  00:00 UTC reset, or supply a paid/SENTRA_LLM_* credential.\n"
        )
    OUT_SAMPLE.write_text(
        json.dumps(
            {
                "spike": "S5",
                "subject": "30-doc quality sample — deterministic heuristic grading",
                "model": _llm.default_model(),
                "grading": {
                    "checks": [
                        "summary_non_empty: summary is at least "
                        f"{SUMMARY_MIN_CHARS} chars",
                        "mentions_qualified_name_or_identifier: the chunk's qualified "
                        "name or any identifier of length >3 appears in the summary",
                        "no_refusal: none of "
                        f"{list(REFUSAL_MARKERS)} appear",
                        "summary_length_within_bounds: between "
                        f"{SUMMARY_MIN_CHARS} and {SUMMARY_MAX_CHARS} chars",
                    ],
                    "deterministic": True,
                },
                "totals": {
                    "docs": len(graded),
                    "passed": sample_pass,
                    "pass_rate_pct": report["quality_sample"]["pass_rate_pct"],
                    "per_check_failures": per_check_fail,
                },
                "docs": graded,
            },
            indent=2,
        )
    )

    print("\n" + "=" * 74)
    print("S5 — DOCUMENTATION GENERATION + COST")
    print("=" * 74)
    print(f"  chunks attempted / succeeded : {attempted} / {len(ok)}")
    print(f"  COVERAGE                     : {coverage:.2f}%  (target >= 95%)  -> "
          f"{'MET' if coverage >= 95.0 else 'NOT MET'}")
    print(f"  LLM calls                    : {llm_calls}  "
          f"({ct['calls_per_chunk']:.2f} calls/chunk)")
    print(f"  wall seconds                 : {ct['wall_seconds']:.1f}  "
          f"({ct['chunks_per_second']:.3f} chunks/s)")
    print(f"  latency per chunk            : mean {ct['mean_latency_s']:.1f}s  "
          f"min {ct['min_latency_s']:.1f}s  max {ct['max_latency_s']:.1f}s")
    if using_chars:
        print(f"  chars in/out                 : {chars_in_total} / {chars_out_total}  "
              f"({ct['chars_in_per_chunk_avg']:.0f}/chunk in, {ct['chars_out_per_chunk_avg']:.0f}/chunk out)")
        print(f"  (cli transport: no token usage; note: {usage_note})")
    elif prompt_tokens:
        print(f"  prompt tokens                : {prompt_tokens} total  "
              f"({ct['prompt_tokens_per_chunk_avg']:.0f}/chunk)")
        print(f"  completion tokens            : {completion_tokens} total  "
              f"({ct['completion_tokens_per_chunk_avg']:.0f}/chunk)")
        print(f"    of which reasoning        : {reasoning_tokens} "
              f"({100.0 * reasoning_tokens / completion_tokens:.1f}% of completion)")
        print(f"    of which document text    : {api_tokens} "
              f"({ct['output_tokens_per_chunk_avg']:.0f}/chunk)")
    print(f"  budget                       : {BUDGET}  -> {report['verdict']['budget_met']}")
    print(f"  QUALITY SAMPLE               : {sample_pass}/{len(graded)} passed "
          f"({report['quality_sample']['pass_rate_pct']:.2f}%)")
    if per_check_fail:
        print(f"    failing checks             : {per_check_fail}")
    if failed:
        print(f"  failures ({len(failed)})            : {report['coverage']['failure_reasons']}")
    print(f"\n  {OUT.relative_to(REPO_ROOT)}\n  {OUT_SAMPLE.relative_to(REPO_ROOT)}")
    return 0


def quota_snapshot() -> dict:
    """Live free-tier quota, for the blocked-run record.

    Cheap and read-only; it is the fact that decides whether a rerun is even
    possible, so it belongs in the evidence rather than in a chat message.
    """
    try:
        import requests as req

        r = req.get(
            "https://openrouter.ai/api/v1/key",
            headers={"Authorization": f"Bearer {_llm.api_key()}"},
            timeout=30,
        )
        return r.json().get("data", {}).get("free_model_daily_requests") or {}
    except Exception as exc:  # noqa: BLE001 - snapshot is best-effort
        return {"error": f"{type(exc).__name__}: {exc}"}


def _repo_commit() -> str | None:
    import subprocess

    try:
        return subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=20,
        ).stdout.strip()
    except Exception:  # pragma: no cover - commit is contextual, not required
        return None


def _count_reasons(failed: list[dict]) -> dict:
    """Bucket failures by cause, not by exception class."""
    out: dict[str, int] = {}
    for r in failed:
        err = r["error"] or ""
        # Drop the exception-class prefix so the bucket names the cause.
        if ": " in err:
            err = err.split(": ", 1)[1]
        key = err.split(":")[0].split("(")[0].strip() or "unknown"
        out[key] = out.get(key, 0) + 1
    return out


if __name__ == "__main__":
    raise SystemExit(main())
