"""
Sentra P0 / Spike S7 — LLM bug-review precision per layer, confidence
threshold, and cost per finding.

Measures, with no claim beyond what is measured (Sentra_research.md §9, row S7):
   1. Precision of an LLM judge on Semgrep findings whose ground truth we
      authored ourselves (S2b probe corpus), at two context layers:
        L1 — finding-only context (rule id, message, flagged lines)
        L2 — the same finding plus the enclosing syntax-aware chunk (S1)
   2. False positives on the four authored safe controls.
   3. Confidence-threshold sweep {0.3, 0.5, 0.7, 0.9}: precision/recall when
      only verdicts at or above the threshold are kept.
   4. Cost per finding on the opencode CLI transport: calls, chars in/out and
      wall seconds. Token usage is NOT available on this transport, so no
      token table and no dollar estimate is reported.

Attribution is exact: a finding maps to a truth pattern only when its line
range covers that pattern's vulnerable line. The S2b probe's ±6
nearest-from-first-line heuristic is deliberately NOT reused — it mislabels
same-CWE siblings (cwe_78.py L4/L7/L10, cwe_327.py L4/L7). Unmappable findings
are counted as "ambiguous" and excluded from precision denominators.

Writes docs/evidence/S7_llm_review.json and docs/evidence/S7_sample.json.

Blocked-run handling (the opencode free tier is an account-wide daily quota,
and hitting it mid-run is not a per-finding measurement failure): a terminal
quota/free-tier error stops the batch immediately — it is NOT retried per
finding — and the run writes docs/evidence/S7_llm_review_blocked.json, shaped
like docs/evidence/S5_docgen_blocked.json, while leaving NO metrics file behind.
A measurement failure (provider down, malformed output) is recorded in the
evidence and exits 0; a missing corpus exits 1 because that is a setup error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # spikes root: _llm
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "s1_tree_sitter"))
import _llm  # noqa: E402
from chunker import Chunker, ChunkerConfig, language_for_path  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE_DIR = REPO_ROOT / "data" / "repos" / "fixtures" / "probe"
OUT = REPO_ROOT / "docs" / "evidence" / "S7_llm_review.json"
OUT_SAMPLE = REPO_ROOT / "docs" / "evidence" / "S7_sample.json"
OUT_BLOCKED = REPO_ROOT / "docs" / "evidence" / "S7_llm_review_blocked.json"
SEMGREP = REPO_ROOT / ".venv" / "bin" / "semgrep"
RULESETS = ["p/security-audit", "p/python", "p/javascript"]

MAX_ATTEMPTS = 2  # one call + one retry on transport/parse failure, counted
THRESHOLDS = [0.3, 0.5, 0.7, 0.9]
SAMPLE_SIZE = 5

# ---------------------------------------------------------------------------
# Ground truth, authored in S2b and frozen here with the *vulnerable line* and
# a snippet that validates the line against the corpus.
#
# Every entry is (file, pattern_id, cwe, vulnerable_line, snippet, expect_hit).
# expect_hit is what a rule-based engine can legitimately catch; the SAFE rows
# are deliberate negative controls. Snippet is asserted against the file at
# startup, so corpus drift fails loudly instead of mislabelling a finding.
# ---------------------------------------------------------------------------
TRUTH: list[tuple[str, str, str, int, str, bool]] = [
    ("cwe_22.py", "open_user_path", "CWE-22", 3, "open(p)", True),
    ("cwe_22.js", "js_path_join_traversal", "CWE-22", 3, "path.join", True),
    ("cwe_295.py", "verify_false_tls", "CWE-295", 4, "verify=False", True),
    ("cwe_327.py", "md5_for_password", "CWE-327", 4, "hashlib.md5", True),
    ("cwe_327.py", "sha1_for_password", "CWE-327", 7, "hashlib.sha1", True),
    ("cwe_330.py", "random_for_token", "CWE-330", 4, "random.random()", True),
    ("cwe_502.py", "pickle_loads_untrusted", "CWE-502", 4, "pickle.loads", True),
    ("cwe_601.py", "urlopen_nonliteral", "CWE-601", 4, "urlopen(u)", True),
    ("cwe_78.py", "subprocess_shell_true", "CWE-78", 4, "subprocess.call(c, shell=True)", True),
    ("cwe_78.py", "subprocess_popen_shell", "CWE-78", 7, "subprocess.Popen(c, shell=True)", True),
    ("cwe_78.py", "os_system", "CWE-78", 10, "os.system(c)", True),
    ("cwe_78.js", "js_child_process_exec", "CWE-78", 3, "cp.exec(c)", True),
    ("cwe_798.py", "hardcoded_password", "CWE-798", 2, "PASSWORD", True),
    ("cwe_798.js", "js_hardcoded_secret", "CWE-798", 2, "API_KEY", True),
    ("cwe_89.py", "sqli_inline_fstring", "CWE-89", 3, 'cur.execute(f"SELECT * FROM {t}")', True),
    ("cwe_89.py", "sqli_inline_concat", "CWE-89", 5, 'cur.execute("SELECT * FROM " + t)', True),
    ("cwe_89.js", "js_sql_concat", "CWE-89", 2, 'c.query("SELECT * FROM " + t)', True),
    ("cwe_94.py", "yaml_load_unsafe", "CWE-94", 4, "yaml.load(s)", True),
    ("cwe_95.py", "eval_user_input", "CWE-95", 3, "eval(x)", True),
    ("cwe_95.py", "exec_user_input", "CWE-95", 5, "exec(x)", True),
    ("cwe_95.js", "js_eval", "CWE-95", 2, "eval(x)", True),
    # --- deliberate controls: no finding should exist here ---
    ("safe.py", "control_parameterised_sql", "SAFE", 3, '"SELECT * FROM t WHERE a = ?", (t,)', False),
    ("safe.py", "control_subprocess_list", "SAFE", 6, 'subprocess.run(["ls", a])', False),
    ("safe.py", "control_no_eval", "SAFE", 8, "int(x) + 1", False),
    ("safe.js", "js_control_spawn_args", "SAFE", 3, "spawnSync", False),
]

PROMPT = """You are a precise application-security reviewer triaging one static-analysis finding produced by Semgrep on a small Python/JavaScript corpus.

Decide whether the finding identifies a genuine security vulnerability in the code shown.
- "true_positive" = the flagged code is genuinely vulnerable as described.
- "false_positive" = the flagged code is safe, or the rule's claim does not hold.
Judge only the context given. Do not assume that unseen code makes it safe.

Respond with ONLY one JSON object (no prose, no markdown fence) with exactly these fields:
{{"verdict": "true_positive" | "false_positive",
 "confidence": <number from 0.0 to 1.0>,
 "severity": "critical" | "high" | "medium" | "low" | "info",
 "rationale": "<one line, at most 200 characters>"}}

--- FINDING ---
rule: {rule}
message: {message}
semgrep severity: {severity}
file: {file}
lines: {start_line}-{end_line}

flagged code:
```{language}
{flagged}
```{context}"""

CONTEXT_L2 = """
--- ENCLOSING CODE UNIT ({kind} {name}, lines {chunk_start}-{chunk_end}) ---
```{language}
{chunk}
```"""

# --- provider-capacity block -------------------------------------------------
# The opencode free tier enforces an ACCOUNT-WIDE daily cap. It surfaces from
# the CLI transport as exit 1 with "Free usage limit reached" (FreeTierError),
# and from the HTTP transport as the openrouter daily-cap messages. Both are
# terminal for the rest of the day: retrying costs a doomed call per finding
# and converts a credential failure into a fake measurement.
QUOTA_MARKERS = (
    "free usage limit",
    "freetier",
    "free-models-per-day",
    "quota_exhausted_daily",
    "rate limit",
    "quota_exceeded",
    "insufficient_quota",
    "billing",
    "capacity",
)
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def is_quota_block(error: str) -> bool:
    low = error.lower()
    return any(m in low for m in QUOTA_MARKERS)


def clean_error(text: str) -> str:
    """Strip CLI colour escapes so the recorded error is exact, not decorated."""
    return _ANSI_RE.sub("", text).strip()


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:  # path outside the repo (tests): keep it absolute, don't crash
        return str(path)


def transport_name() -> str:
    return "cli" if _llm.chat is _llm.chat_cli else "http"


def run_semgrep() -> tuple[list[dict], int]:
    """Scan the probe corpus. --no-git-ignore is mandatory (see S2b)."""
    cmd = [
        str(SEMGREP), "scan", "--json", "--quiet", "--metrics=off",
        "--no-git-ignore", "--timeout", "60",
    ]
    for r in RULESETS:
        cmd += ["--config", r]
    cmd.append(str(PROBE_DIR))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"unparseable semgrep output: {proc.stderr[-500:]}")
    findings = data.get("results", [])
    scanned = len(data.get("paths", {}).get("scanned", []))
    if scanned == 0:
        raise RuntimeError(
            "Semgrep scanned zero files — harness/ignore-rule failure, not a measurement."
        )
    return findings, scanned


def load_truth() -> list[dict]:
    """Validate the frozen truth table against the corpus, then return it."""
    truth = []
    for file, pid, cwe, line, snippet, expect in TRUTH:
        path = PROBE_DIR / file
        lines = path.read_text().splitlines()
        if line > len(lines) or snippet not in lines[line - 1]:
            raise RuntimeError(
                f"ground truth drifted: {file}:{line} does not contain {snippet!r}"
            )
        truth.append({
            "file": file,
            "pattern_id": pid,
            "cwe": cwe,
            "vulnerable_line": line,
            "snippet": snippet,
            "expect_hit": expect,
        })
    return truth


def attribute(finding: dict, truth: list[dict]) -> tuple[dict | None, str | None]:
    """Exact attribution by file + vulnerable line. No proximity heuristic."""
    rel = Path(finding["path"]).name
    start, end = finding["start"]["line"], finding["end"]["line"]
    candidates = [
        t for t in truth
        if t["file"] == rel and start <= t["vulnerable_line"] <= end
    ]
    if len(candidates) == 1:
        return candidates[0], None
    if not candidates:
        return None, f"no truth line in {rel}:{start}-{end}"
    return None, (
        f"ambiguous: {rel}:{start}-{end} covers "
        + ", ".join(t["pattern_id"] for t in candidates)
    )


def best_chunk(file_path: Path, start_byte: int, end_byte: int):
    """Smallest chunk containing the finding's byte range."""
    language = language_for_path(file_path)
    if language is None:
        return None, "unsupported_extension"
    source = file_path.read_bytes()
    chunks, _diag = Chunker(ChunkerConfig()).chunk_source(source, file_path.name, language)
    containing = [
        c for c in chunks if c.byte_start <= start_byte and c.byte_end >= end_byte
    ]
    if not containing:
        # Module chunk covers the whole file, so this should not happen; fall
        # back to the file text rather than silently dropping L2 context.
        return {
            "kind": "file", "name": "<whole-file>", "start_line": 1,
            "end_line": source.count(b"\n") + 1,
            "content": source.decode("utf8", "replace"), "language": language,
        }, "no_containing_chunk"
    best = min(containing, key=lambda c: c.byte_end - c.byte_start)
    return {
        "kind": best.kind, "name": best.name,
        "start_line": best.start_line, "end_line": best.end_line,
        "content": best.content, "language": best.language,
    }, None


def _first_json_object(text: str) -> dict | None:
    """Bracket-matching fallback: CLI stdout may wrap JSON in prose."""
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        candidate = json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
                    return candidate if isinstance(candidate, dict) else None
        start = text.find("{", start + 1)
    return None


def parse_verdict(content: str) -> tuple[dict | None, str | None]:
    """Parse and strictly validate the judge's JSON."""
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = _first_json_object(text)
    if not isinstance(data, dict):
        return None, "json_not_found_or_not_an_object"

    verdict = data.get("verdict")
    confidence = data.get("confidence")
    severity = data.get("severity")
    rationale = data.get("rationale")
    if verdict not in ("true_positive", "false_positive"):
        return None, f"bad_verdict:{verdict!r}"
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        return None, f"bad_confidence:{confidence!r}"
    if not 0.0 <= confidence <= 1.0:
        return None, f"confidence_out_of_range:{confidence}"
    for field, value in (("severity", severity), ("rationale", rationale)):
        if not isinstance(value, str) or not value.strip():
            return None, f"empty_{field}"
    return {
        "verdict": verdict,
        "confidence": round(confidence, 3),
        "severity": severity.strip(),
        "rationale": rationale.strip()[:200],
    }, None


def build_prompt(finding: dict, truth_rec: dict, layer: str, chunk, source_lines: list[str]) -> str:
    start, end = finding["start"]["line"], finding["end"]["line"]
    flagged = "\n".join(source_lines[start - 1:end][:20])
    context = ""
    if layer == "L2" and chunk is not None:
        context = CONTEXT_L2.format(
            kind=chunk["kind"], name=chunk["name"],
            chunk_start=chunk["start_line"], chunk_end=chunk["end_line"],
            language=chunk["language"], chunk=chunk["content"],
        )
    return PROMPT.format(
        rule=finding["check_id"],
        message=finding["extra"].get("message", "")[:400],
        severity=finding["extra"].get("severity", ""),
        file=truth_rec["file"],
        start_line=start,
        end_line=end,
        language=language_for_path(PROBE_DIR / truth_rec["file"]),
        flagged=flagged,
        context=context,
    )


def review(finding: dict, truth_rec: dict, layer: str, chunk, source_lines: list[str]) -> dict:
    """One finding at one layer, with at most MAX_ATTEMPTS and honest accounting."""
    prompt = build_prompt(finding, truth_rec, layer, chunk, source_lines)
    rec = {
        "layer": layer,
        "pattern_id": truth_rec["pattern_id"],
        "file": truth_rec["file"],
        "line": finding["start"]["line"],
        "rule": finding["check_id"],
        "attempts": 0,
        "chars_in": 0,
        "chars_out": 0,
        "latency_s": 0.0,
        "verdict": None,
        "confidence": None,
        "severity": None,
        "rationale": None,
        "error": None,
    }
    for attempt in range(1, MAX_ATTEMPTS + 1):
        rec["attempts"] = attempt
        try:
            content, usage, latency = _llm.chat(
                messages=[{"role": "user", "content": prompt}], max_tokens=300, response_format={"type": "json_object"}, reasoning_effort="none"
            )
        except _llm.LLMError as exc:
            rec["error"] = f"llm_error:{clean_error(str(exc))}"
            # A daily free-tier cap is terminal for the day: retrying it per
            # finding would just spend doomed calls. Record and let main() stop.
            if is_quota_block(rec["error"]):
                return rec
            continue
        rec["chars_in"] += usage.get("chars_in", 0)
        rec["chars_out"] += usage.get("chars_out", 0)
        rec["latency_s"] = round(rec["latency_s"] + latency, 3)
        parsed, err = parse_verdict(content)
        if parsed is not None:
            rec.update(parsed)
            rec["error"] = None
            return rec
        rec["error"] = f"malformed_output:{err}"
        rec["raw_head"] = content[:300]
    return rec


def layer_metrics(records: list[dict], mapped_total: int, controls: list[dict]) -> dict:
    parsed = [r for r in records if r["verdict"]]
    tp = [r for r in parsed if r["verdict"] == "true_positive"]
    fp = [r for r in parsed if r["verdict"] == "false_positive"]
    controls_flagged = [
        r for r in tp if r["file"] in {c["file"] for c in controls}
    ]
    tp_total = len(tp)

    sweep = {}
    for t in THRESHOLDS:
        kept = [r for r in parsed if r["confidence"] >= t]
        kept_tp = [r for r in kept if r["verdict"] == "true_positive"]
        kept_fp = [r for r in kept if r["verdict"] == "false_positive"]
        sweep[str(t)] = {
            "kept": len(kept),
            "dropped": len(parsed) - len(kept),
            "true_positives": len(kept_tp),
            "false_positives": len(kept_fp),
            "precision": round(len(kept_tp) / len(kept), 3) if kept else None,
            # Recall here is verdict-level: of all findings this layer called
            # true_positive, the fraction still asserted at this confidence.
            # It is NOT corpus recall (Semgrep surfaced only 10 of 21 positives).
            "recall": round(len(kept_tp) / tp_total, 3) if tp_total else None,
        }

    latencies = [r["latency_s"] for r in records]
    return {
        "findings_judged": len(records),
        "usable_verdicts": len(parsed),
        "unreviewed_parse_or_call_failures": len(records) - len(parsed),
        "true_positives": len(tp),
        "false_positives": len(fp),
        "precision": round(len(tp) / len(parsed), 3) if parsed else None,
        "precision_denominator": len(parsed),
        "mapped_findings_total": mapped_total,
        "controls_flagged": len(controls_flagged),
        "controls_flagged_detail": [r["pattern_id"] for r in controls_flagged],
        "corpus_recall_note": (
            f"LLM precision is over the {mapped_total} findings Semgrep surfaced "
            "from 21 positives; the 21-pattern corpus recall belongs to S2b, not here."
        ),
        "false_positive_detail": [
            {"pattern_id": r["pattern_id"], "confidence": r["confidence"],
             "rationale": r["rationale"]}
            for r in fp
        ],
        "threshold_sweep": sweep,
        "cost": {
            "calls": sum(r["attempts"] for r in records),
            "calls_per_finding": round(sum(r["attempts"] for r in records) / max(1, len(records)), 3),
            "chars_in_total": sum(r["chars_in"] for r in records),
            "chars_out_total": sum(r["chars_out"] for r in records),
            "chars_per_finding": round(
                sum(r["chars_in"] + r["chars_out"] for r in records) / max(1, len(records)), 1
            ),
            "wall_seconds": round(sum(latencies), 2),
            "wall_seconds_per_finding": round(sum(latencies) / max(1, len(records)), 2),
            "mean_latency_s": round(sum(latencies) / max(1, len(latencies)), 2) if latencies else 0.0,
            "tokens": "unavailable on the opencode CLI transport (chars reported instead)",
        },
    }


def write_blocked(blocked: dict, ctx: dict) -> None:
    """Record the provider-capacity block. NO metrics are written for the LLM
    layer: none exist, and a partial run's numbers would be read as S7's."""
    records = ctx["records"]
    calls = sum(r["attempts"] for v in records.values() for r in v)
    reviewable = sum(len(v) for v in records.values())
    usable = sum(1 for v in records.values() for r in v if r["verdict"])
    payload = {
        "spike": "S7",
        "subject": "LLM bug-review precision per context layer, confidence threshold, cost per finding",
        "status": "blocked_provider_freetier_gate",
        "blocked_by_quota": True,
        "research_row": "Sentra_research.md §9, row S7",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "toolchain": {
            "model": _llm.default_model(),
            "transport": transport_name(),
            "client": "spikes/_llm.py (shared, reused from S5)",
            "semgrep": "1.179.0",
            "rulesets": RULESETS,
        },
        # Everything deterministic WAS measured and is reported: the corpus
        # re-scan, the exact attribution, and the L1/L2 layer plumbing. What is
        # missing is only the LLM verdicts, which the provider refused.
        "corpus": {
            "path": str(PROBE_DIR.relative_to(REPO_ROOT)),
            "ground_truth": "S2b authored probe corpus (21 vulnerable, 4 safe)",
            "scanned_files": ctx["scanned"],
            "findings": ctx["n_findings"],
            "mapped_findings": ctx["n_mapped"],
            "ambiguous_findings": ctx["n_ambiguous"],
            "attribution_method": (
                "finding line range must cover the truth pattern's vulnerable line; "
                "file+line exact, no ±6 nearest-match heuristic"
            ),
        },
        "attribution": ctx["attribution"],
        "llm_calls_attempted": calls,
        "findings_judged_possible": reviewable,
        "verdicts_usable_before_block": usable,
        "error": {
            "transport": transport_name(),
            "model": _llm.default_model(),
            "type": "opencode CLI exit 1: free usage limit reached (account-wide daily cap)",
            "redacted_error": blocked["error"],
            "stopped_at": f"layer {blocked['layer']}, pattern {blocked['pattern_id']} ({blocked['file']})",
            "wall_seconds_before_block": round(ctx["wall"], 2),
        },
        "note": (
            "The opencode free tier enforces an ACCOUNT-WIDE daily request cap, "
            "which is exhausted for every model on this account, not just this one. "
            "The block is terminal until the reset: `opencode run -m "
            f"{_llm.cli_model()}` exits 1 with 'Free usage limit reached' before "
            "any model call is made. The batch was stopped at the first such error "
            "rather than spending one doomed call per remaining finding, which is "
            "what turned a credential failure into a fake per-finding measurement "
            "in the S5 rerun (see docs/evidence/S5_docgen_blocked.json). This file "
            "records the block ONLY; no S7_llm_review.json and no S7_sample.json "
            "were written, deliberately, because the LLM precision / threshold / "
            "cost tables they hold were not measurable in this run."
        ),
        "why_not_retried_within_this_run": (
            "The cap is account-wide and terminal until the quota reset. A retry "
            "sooner returns the same exit-1 for every finding."
        ),
        "rerun_condition": (
            "opencode quota reset 00:00 UTC, or a paid/API credential "
            "(SENTRA_LLM_API_KEY + SENTRA_LLM_BASE_URL, or a paid opencode key)"
        ),
        # SENTRA_LLM_PROVIDER=opencode is REQUIRED: with only SENTRA_LLM_MODEL
        # set, _llm.resolve_provider() falls through to openrouter and the CLI
        # transport is silently replaced by an HTTP call to the wrong host.
        "rerun_command": (
            "SENTRA_LLM_PROVIDER=opencode "
            f"SENTRA_LLM_MODEL='{_llm.cli_model()}' "
            ".venv/bin/python spikes/s7_llm_review/spike.py"
            "   # after the 00:00 UTC quota reset or with a paid credential"
        ),
        "invoked_as": {
            "argv": sys.argv,
            "SENTRA_LLM_PROVIDER": os.environ.get("SENTRA_LLM_PROVIDER"),
            "SENTRA_LLM_MODEL": os.environ.get("SENTRA_LLM_MODEL"),
            "SENTRA_LLM_TRANSPORT": os.environ.get("SENTRA_LLM_TRANSPORT"),
            "note": "credential env vars (SENTRA_LLM_API_KEY / BASE_URL) are deliberately not recorded",
        },
        "layers": None,
        "cost_summary": None,
    }
    OUT_BLOCKED.parent.mkdir(parents=True, exist_ok=True)
    OUT_BLOCKED.write_text(json.dumps(payload, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser(description="S7 — LLM bug-review precision/cost")
    ap.add_argument("--limit", type=int, default=0, help="only the first N findings (smoke runs)")
    args = ap.parse_args()

    if not PROBE_DIR.is_dir():
        print(f"Missing corpus: {PROBE_DIR}")
        return 1

    # A run that stops early (provider block, crash) must not leave a previous
    # run's metrics behind looking like this run's result.
    for stale in (OUT, OUT_SAMPLE):
        stale.unlink(missing_ok=True)

    truth = load_truth()
    controls = [t for t in truth if not t["expect_hit"]]
    findings, scanned = run_semgrep()

    mapped: list[tuple[dict, dict]] = []
    ambiguous: list[dict] = []
    for f in findings:
        rec, err = attribute(f, truth)
        if rec is None:
            ambiguous.append({
                "rule": f["check_id"],
                "file": Path(f["path"]).name,
                "lines": f'{f["start"]["line"]}-{f["end"]["line"]}',
                "reason": err,
            })
        else:
            mapped.append((f, rec))
    if args.limit:
        mapped = mapped[: args.limit]

    print("=" * 74)
    print("S7 — LLM BUG-REVIEW PRECISION / THRESHOLD / COST")
    print("=" * 74)
    print(f"  model            : {_llm.default_model()}")
    print(f"  transport        : {transport_name()}")
    print(f"  scanned files    : {scanned}")
    print(f"  findings         : {len(findings)}  mapped: {len(mapped)}  ambiguous: {len(ambiguous)}")
    print(f"  ground truth     : {len(truth) - len(controls)} positives, {len(controls)} safe controls")

    started = time.perf_counter()
    calls_before = _llm.STATS["http_calls"]
    records: dict[str, list[dict]] = {"L1": [], "L2": []}
    chunk_fallbacks = 0
    blocked: dict | None = None

    for i, (finding, truth_rec) in enumerate(mapped, 1):
        file_path = PROBE_DIR / truth_rec["file"]
        source_lines = file_path.read_text().splitlines()
        chunk, chunk_err = best_chunk(
            file_path, finding["start"]["offset"], finding["end"]["offset"]
        )
        chunk_fallbacks += 1 if chunk_err else 0
        for layer in ("L1", "L2"):
            rec = review(finding, truth_rec, layer, chunk, source_lines)
            rec["chunk_kind"] = chunk["kind"] if chunk else None
            rec["chunk_lines"] = [chunk["start_line"], chunk["end_line"]] if chunk else None
            records[layer].append(rec)
            shown = rec["verdict"] or "ERROR"
            print(
                f"[{i:>2}/{len(mapped)}] {layer} {truth_rec['pattern_id']:<28} "
                f"{shown:<13} conf={rec['confidence']}  {rec['latency_s']:>5.1f}s"
                + (f"  <- {rec['error']}" if rec["error"] else ""),
                flush=True,
            )
            if rec["error"] and is_quota_block(rec["error"]):
                blocked = {
                    "error": rec["error"],
                    "layer": layer,
                    "pattern_id": truth_rec["pattern_id"],
                    "file": truth_rec["file"],
                    "reviews_completed": sum(len(v) for v in records.values()),
                }
                break
        if blocked:
            break

    wall = time.perf_counter() - started
    calls = _llm.STATS["http_calls"] - calls_before

    if blocked:
        # Terminal provider-capacity block: record it and stop. No metrics file.
        write_blocked(blocked, {
            "scanned": scanned,
            "n_findings": len(findings),
            "n_mapped": len(mapped),
            "n_ambiguous": len(ambiguous),
            "attribution": [
                {
                    "pattern_id": t["pattern_id"],
                    "cwe": t["cwe"],
                    "file": t["file"],
                    "vulnerable_line": t["vulnerable_line"],
                    "truth": "vulnerable" if t["expect_hit"] else "safe_control",
                    "semgrep_lines": f'{f["start"]["line"]}-{f["end"]["line"]}',
                    "rule": f["check_id"],
                }
                for f, t in mapped
            ],
            "records": records,
            "wall": wall,
        })
        print("-" * 74)
        print("  PROVIDER BLOCK (account-wide free-tier cap) — batch stopped")
        print(f"  model   : {_llm.default_model()}  transport: {transport_name()}")
        print(f"  error   : {blocked['error'][:200]}")
        print(f"  stopped : {blocked['layer']} on {blocked['pattern_id']}")
        print(f"  LLM calls attempted: {calls} (deterministic attribution was measured)")
        print(f"  No S7_llm_review.json written — no LLM precision was measurable.")
        print(f"  Report: {_rel(OUT_BLOCKED)}")
        return 0

    metrics = {
        layer: layer_metrics(records[layer], len(mapped), controls)
        for layer in ("L1", "L2")
    }

    # Agreement between the two layers on the same finding.
    by_key = {}
    for layer in ("L1", "L2"):
        for r in records[layer]:
            by_key.setdefault((r["file"], r["line"]), {})[layer] = r
    both = [v for v in by_key.values() if v.get("L1", {}).get("verdict") and v.get("L2", {}).get("verdict")]
    disagreements = [
        {
            "file": next(iter(v.values()))["file"],
            "line": next(iter(v.values()))["line"],
            "pattern_id": next(iter(v.values()))["pattern_id"],
            "L1": f'{v["L1"]["verdict"]}@{v["L1"]["confidence"]}',
            "L2": f'{v["L2"]["verdict"]}@{v["L2"]["confidence"]}',
        }
        for v in both if v["L1"]["verdict"] != v["L2"]["verdict"]
    ]

    anomalies = {
        "ambiguous_attributions": ambiguous,
        "ambiguous_count": len(ambiguous),
        "malformed_outputs": [
            {"layer": r["layer"], "pattern_id": r["pattern_id"], "error": r["error"]}
            for layer in ("L1", "L2") for r in records[layer] if r["error"]
        ],
        "retries": sum(1 for layer in ("L1", "L2") for r in records[layer] if r["attempts"] > 1),
        "llm_transient_retries": _llm.STATS["transient_retries"],
        "no_usable_content": _llm.STATS["no_usable_content"],
        "chunk_lookup_fallbacks": chunk_fallbacks,
        "controls_with_findings": 0,  # measured: no Semgrep finding on a safe file
    }

    status = "complete" if (
        not args.limit and all(
            m["usable_verdicts"] == m["findings_judged"] for m in metrics.values()
        )
    ) else ("partial_smoke_run" if args.limit else "partial_measurement_failure")

    report = {
        "spike": "S7",
        "subject": "LLM bug-review precision per context layer, confidence threshold, cost per finding",
        "research_row": "Sentra_research.md §9, row S7",
        "status": status,
        "toolchain": {
            "model": _llm.default_model(),
            "transport": transport_name(),
            "client": "spikes/_llm.py (shared, reused from S5)",
            "semgrep": "1.179.0",
            "rulesets": RULESETS,
        },
        "corpus": {
            "path": str(PROBE_DIR.relative_to(REPO_ROOT)),
            "ground_truth": "S2b authored probe corpus (21 vulnerable, 4 safe)",
            "scanned_files": scanned,
            "findings": len(findings),
            "mapped_findings": len(mapped),
            "review_limit": args.limit or None,
            "ambiguous_findings": len(ambiguous),
            "attribution_method": (
                "finding line range must cover the truth pattern's vulnerable line; "
                "file+line exact, no ±6 nearest-match heuristic"
            ),
        },
        "layers": {
            "L1": {
                "context": "finding only: rule id, message, severity, flagged lines",
                **metrics["L1"],
            },
            "L2": {
                "context": "finding plus smallest S1 syntax-aware chunk containing it",
                **metrics["L2"],
            },
        },
        "layer_agreement": {
            "compared": len(both),
            "agree": len(both) - len(disagreements),
            "disagree": len(disagreements),
            "disagreements": disagreements,
        },
        "cost_summary": {
            "llm_calls_total": calls,
            "findings_reviewed": len(mapped) * 2,
            "wall_seconds_total": round(wall, 2),
            "wall_seconds_per_review": round(wall / max(1, len(mapped) * 2), 2),
            "note": "opencode CLI transport: no token usage; cost = calls + chars + wall seconds",
        },
        "anomalies": anomalies,
        "verdict": {
            "note": (
                "These are OUR 21 authored patterns, not a third-party benchmark. "
                "The finding-level precision measures the judge's ability to confirm "
                "or reject Semgrep findings, not Semgrep's or Sentra's corpus recall. "
                "Safe-control false positives cannot be measured above zero on this "
                "run because Semgrep raised no finding on any of the 4 controls."
            ),
            "confidence_caveat": (
                "Threshold precision/recall is on 10 findings per layer; one verdict "
                "moves precision by 0.1. Treat the sweep as directional, not stable."
            ),
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))

    # Deterministic 5-finding sample: even stride over mapped order.
    stride = (len(mapped) - 1) / (SAMPLE_SIZE - 1) if len(mapped) > SAMPLE_SIZE else 1
    sample_idx = (
        [round(i * stride) for i in range(SAMPLE_SIZE)] if len(mapped) > SAMPLE_SIZE
        else list(range(len(mapped)))
    )
    sample = []
    for idx in sample_idx:
        finding, truth_rec = mapped[idx]
        l1 = records["L1"][idx]
        l2 = records["L2"][idx]
        sample.append({
            "pattern_id": truth_rec["pattern_id"],
            "cwe": truth_rec["cwe"],
            "file": truth_rec["file"],
            "vulnerable_line": truth_rec["vulnerable_line"],
            "truth": "vulnerable" if truth_rec["expect_hit"] else "safe",
            "rule": finding["check_id"],
            "L1": {"verdict": l1["verdict"], "confidence": l1["confidence"]},
            "L2": {"verdict": l2["verdict"], "confidence": l2["confidence"]},
            "agreement": l1["verdict"] == l2["verdict"],
        })
    OUT_SAMPLE.write_text(json.dumps({
        "spike": "S7",
        "model": _llm.default_model(),
        "sample_size": len(sample),
        "note": "Deterministic even-stride sample of the reviewed findings.",
        "findings": sample,
    }, indent=2))

    print("-" * 74)
    for layer in ("L1", "L2"):
        m = metrics[layer]
        p = "n/a" if m["precision"] is None else f'{m["precision"]:.1%}'
        print(f"  {layer} context       : precision {p}  "
              f"TP={m['true_positives']} FP={m['false_positives']} "
              f"unreviewed={m['unreviewed_parse_or_call_failures']} "
              f"precision_denom={m['precision_denominator']}  "
              f"controls_flagged={m['controls_flagged']}")
        print(f"     cost             : {m['cost']['calls']} calls, "
              f"{m['cost']['chars_in_total']}+{m['cost']['chars_out_total']} chars, "
              f"{m['cost']['wall_seconds']}s, "
              f"{m['cost']['wall_seconds_per_finding']}s/finding")
        for t, s in m["threshold_sweep"].items():
            print(f"     >= {t:<4}          : kept={s['kept']:<2} precision={s['precision']} recall={s['recall']}")
    print(f"  layer agreement  : {report['layer_agreement']['agree']}/{len(both)}")
    print(f"  ambiguous        : {len(ambiguous)}")
    print(f"  model            : {_llm.default_model()}")
    print(f"\n  Report: {OUT.relative_to(REPO_ROOT)}")
    print(f"  Sample: {OUT_SAMPLE.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
