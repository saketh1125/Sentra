"""
Sentra P0 / Spike S2b — Semgrep CE detection probe on a ground-truth corpus.

Motivation (from the S2 exploratory run): scanning requests/flask/axios with
p/security-audit + p/python + p/javascript produced only 13 findings, all
severity WARNING, and did NOT flag a textbook SQL-injection fixture. The
documentation advertises "2,000+ community rules". The gap between the
advertised coverage and the observed coverage is a decision-critical unknown
for D9 (Semgrep rule configuration) and for objective O3 (detection recall).

This module therefore measures detection against patterns whose ground truth
we author ourselves: each pattern is a known-vulnerable snippet at a known
line, so BOTH recall and precision can be computed without human labelling
ambiguity. Human judgement is still applied afterwards to the real-repo
findings in S2's main report.

Authoring rule: every pattern below is deliberately, unambiguously vulnerable
or deliberately safe. We never guess.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "docs" / "evidence" / "S2b_semgrep_probe.json"
SEMGREP = REPO_ROOT / ".venv" / "bin" / "semgrep"
PROBE_DIR = REPO_ROOT / "data" / "repos" / "fixtures" / "probe"

RULESETS = ["p/security-audit", "p/python", "p/javascript"]

# ---------------------------------------------------------------------------
# Ground-truth corpus.
#
# Each entry: (cwe, pattern_id, language, filename, source, expect_detected)
# expect_detected is what a rule-based engine CAN legitimately catch with
# intra-procedural pattern matching. Patterns marked False are the deliberate
# controls — Semgrep is not expected to find them, and finding them would
# itself be a signal worth recording.
# ---------------------------------------------------------------------------

PYTHON_PATTERNS: list[tuple[str, str, str, bool]] = [
    # (cwe, pattern_id, source, expect_detected)
    ("CWE-89", "sqli_inline_fstring",
     'def q(cur, t):\n    cur.execute(f"SELECT * FROM {t}")\n', True),
    ("CWE-89", "sqli_inline_concat",
     'def q(cur, t):\n    cur.execute("SELECT * FROM " + t)\n', True),
    ("CWE-78", "subprocess_shell_true",
     'import subprocess\ndef r(c):\n    subprocess.call(c, shell=True)\n', True),
    ("CWE-78", "subprocess_popen_shell",
     'import subprocess\ndef r(c):\n    subprocess.Popen(c, shell=True)\n', True),
    ("CWE-78", "os_system",
     'import os\ndef r(c):\n    os.system(c)\n', True),
    ("CWE-95", "eval_user_input",
     'def f(x):\n    return eval(x)\n', True),
    ("CWE-95", "exec_user_input",
     'def f(x):\n    exec(x)\n', True),
    ("CWE-22", "open_user_path",
     'def f(p):\n    return open(p).read()\n', True),
    ("CWE-327", "md5_for_password",
     'import hashlib\ndef f(p):\n    return hashlib.md5(p.encode()).hexdigest()\n', True),
    ("CWE-327", "sha1_for_password",
     'import hashlib\ndef f(p):\n    return hashlib.sha1(p.encode()).hexdigest()\n', True),
    ("CWE-798", "hardcoded_password",
     'PASSWORD = "hunter2supersecret"\n', True),
    ("CWE-330", "random_for_token",
     'import random\ndef f():\n    return random.random()\n', True),
    ("CWE-502", "pickle_loads_untrusted",
     'import pickle\ndef f(b):\n    return pickle.loads(b)\n', True),
    ("CWE-94", "yaml_load_unsafe",
     'import yaml\ndef f(s):\n    return yaml.load(s)\n', True),
    ("CWE-295", "verify_false_tls",
     'import requests\ndef f():\n    return requests.get("https://x", verify=False)\n', True),
    ("CWE-601", "urlopen_nonliteral",
     'def f(u):\n    import urllib.request\n    return urllib.request.urlopen(u)\n', True),
    # --- DELIBERATE CONTROLS: Semgrep should NOT flag these. ---
    ("SAFE", "control_parameterised_sql",
     'def q(cur, t):\n    cur.execute("SELECT * FROM t WHERE a = ?", (t,))\n', False),
    ("SAFE", "control_subprocess_list",
     'import subprocess\ndef r(a):\n    subprocess.run(["ls", a])\n', False),
    ("SAFE", "control_no_eval",
     'def f(x):\n    return int(x) + 1\n', False),
]

JS_PATTERNS: list[tuple[str, str, str, bool]] = [
    ("CWE-78", "js_child_process_exec",
     'const cp = require("child_process");\nfunction r(c){ cp.exec(c); }\n', True),
    ("CWE-89", "js_sql_concat",
     'function q(c,t){ c.query("SELECT * FROM " + t); }\n', True),
    ("CWE-95", "js_eval",
     'function f(x){ return eval(x); }\n', True),
    ("CWE-798", "js_hardcoded_secret",
     'const API_KEY = "sk_live_9f8a7b6c5d4e3f2a";\n', True),
    ("CWE-22", "js_path_join_traversal",
     'const path=require("path");\nfunction f(p){ return path.join("/data", p); }\n', True),
    ("SAFE", "js_control_spawn_args",
     'const cp=require("child_process");\nfunction r(a){ cp.spawnSync("ls", a); }\n', False),
]


def write_corpus() -> list[dict]:
    """Materialise the corpus and record the exact line each pattern sits on."""
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    truth: list[dict] = []

    for ext, patterns in ((".py", PYTHON_PATTERNS), (".js", JS_PATTERNS)):
        by_cwe: dict[str, list[tuple[str, str, str, bool]]] = {}
        for cwe, pid, src, expect in patterns:
            by_cwe.setdefault(cwe, []).append((cwe, pid, src, expect))
        # One file per CWE keeps a missed rule from being masked by a
        # neighbouring line, and makes ground-truth line numbers exact.
        for cwe, items in by_cwe.items():
            fname = f"{cwe.lower().replace('-', '_')}{ext}"
            path = PROBE_DIR / fname
            header = (
                f"// Sentra P0 probe corpus - {cwe}\n"
                if ext == ".js"
                else f"# Sentra P0 probe corpus - {cwe}\n"
            )
            body = []
            for _, pid, src, expect in items:
                first = src.split("\n", 1)[-1] if src.count("\n") == 1 else None
                body.append((pid, expect, src))
            # Build with known line offsets (header is line 1).
            text = header
            offsets: list[tuple[str, int, bool]] = []
            line_no = 1
            for pid, expect, src in body:
                src_lines = src.rstrip("\n").split("\n")
                start = line_no + 1
                for sl in src_lines:
                    text += sl + "\n"
                    line_no += 1
                offsets.append((pid, start, expect))
            path.write_text(text)
            for pid, start, expect in offsets:
                truth.append(
                    {
                        "file": str(path.relative_to(REPO_ROOT)),
                        "pattern_id": pid,
                        "first_line": start,
                        "expect_detected": expect,
                    }
                )
    return truth


def run(rulesets: list[str], target: Path) -> list[dict]:
    # --no-git-ignore is MANDATORY, not cosmetic.
    # Sentra's own .gitignore ignores data/repos/*, so a default Semgrep
    # invocation silently scans NOTHING and reports zero findings with exit
    # code 0. That produced a false 0/21 recall in the first run of this probe.
    # Recorded as an integration hazard for P1/P2: any external tool invoked
    # against an ingested repo must be told explicitly to ignore VCS ignore
    # rules, and a zero-scanned-file result must be treated as a harness
    # failure rather than a capability measurement.
    cmd = [
        str(SEMGREP), "scan", "--json", "--quiet", "--metrics=off",
        "--no-git-ignore", "--timeout", "60",
    ]
    for r in rulesets:
        cmd += ["--config", r]
    cmd.append(str(target))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"unparseable semgrep output: {proc.stderr[-500:]}")
    results = data.get("results", [])
    scanned = len(data.get("paths", {}).get("scanned", []))
    if scanned == 0 and not results:
        raise RuntimeError(
            "Semgrep scanned zero files. Refusing to report a 0% result: this is "
            "a harness/ignore-rule failure, not a capability measurement."
        )
    return results


def main() -> int:
    truth = write_corpus()
    t0 = time.perf_counter()
    findings = run(RULESETS, PROBE_DIR)
    elapsed = time.perf_counter() - t0

    # Map each finding to a truth record by file + line proximity.
    matched: dict[str, dict] = {}
    unmatched_findings: list[dict] = []
    for f in findings:
        path = str(Path(f["path"]))
        line = f["start"]["line"]
        best, best_dist = None, 10**9
        for t in truth:
            if not path.endswith(t["file"]):
                continue
            d = abs(line - t["first_line"])
            if d < best_dist:
                best, best_dist = t, d
        rec = {
            "check_id": f["check_id"],
            "severity": f["extra"]["severity"],
            "file": path,
            "line": line,
            "message": f["extra"]["message"][:120],
            "confidence": f["extra"].get("metadata", {}).get("confidence"),
        }
        if best is not None and best_dist <= 6:
            matched[best["pattern_id"]] = rec
        else:
            unmatched_findings.append(rec)

    positive = [t for t in truth if t["expect_detected"]]
    negative = [t for t in truth if not t["expect_detected"]]

    tp = [p for p in positive if p["pattern_id"] in matched]
    fn = [p for p in positive if p["pattern_id"] not in matched]
    fp_control = [p for p in negative if p["pattern_id"] in matched]

    sev_counts = Counter(f["extra"]["severity"] for f in findings)
    conf_counts = Counter(
        f["extra"].get("metadata", {}).get("confidence") for f in findings
    )

    report = {
        "spike": "S2b",
        "subject": "Semgrep CE detection rate on a self-authored ground-truth corpus",
        "purpose": (
            "Measure what CE actually detects, to inform D9 (rule configuration) "
            "and to give objective grounding for the O3 recall target."
        ),
        "toolchain": {"semgrep": "1.179.0"},
        "rulesets": RULESETS,
        "corpus": {
            "positive_patterns": len(positive),
            "negative_control_patterns": len(negative),
            "languages": ["Python", "JavaScript"],
        },
        "results": {
            "true_positives": len(tp),
            "false_negatives": len(fn),
            "false_positives_on_controls": len(fp_control),
            "precision_on_positives": round(len(tp) / max(1, len(tp) + len(unmatched_findings)), 3),
            "recall_on_positives": round(len(tp) / max(1, len(positive)), 3),
            "control_specificity": round(
                (len(negative) - len(fp_control)) / max(1, len(negative)), 3
            ),
            "seconds": round(elapsed, 2),
        },
        "recall_detail": {
            "detected": sorted(p["pattern_id"] for p in tp),
            "missed": sorted(p["pattern_id"] for p in fn),
            "controls_flagged_incorrectly": sorted(p["pattern_id"] for p in fp_control),
        },
        "findings_on_unmatched_locations": unmatched_findings,
        "severity_distribution": dict(sev_counts),
        "confidence_distribution": {str(k): v for k, v in conf_counts.items()},
        "verdict": {
            "note": (
                "These are OUR patterns, not a third-party benchmark. They measure "
                "engine+ruleset capability on patterns we are confident about. "
                "They are NOT a claim about real-world recall, and must not be "
                "presented as one."
            )
        },
    }
    OUT.write_text(json.dumps(report, indent=2))

    r = report["results"]
    print("=" * 70)
    print("S2b — SEMGREP CE DETECTION PROBE (ground truth authored by us)")
    print("=" * 70)
    print(f"  corpus: {len(positive)} vulnerable patterns, {len(negative)} safe controls")
    print(f"  recall on positives        : {r['recall_on_positives']:.1%}  ({len(tp)}/{len(positive)})")
    print(f"  control specificity        : {r['control_specificity']:.1%}")
    print(f"  precision on positives     : {r['precision_on_positives']:.1%}")
    print(f"  severity values seen       : {dict(sev_counts)}")
    print(f"  confidence values seen     : {dict(conf_counts)}")
    print("-" * 70)
    print("  DETECTED:")
    for p in sorted(p['pattern_id'] for p in tp):
        print(f"    + {p}")
    print("  MISSED:")
    for p in sorted(p['pattern_id'] for p in fn):
        print(f"    - {p}")
    if fp_control:
        print("  SAFE CONTROLS FLAGGED (false positives):")
        for p in sorted(p['pattern_id'] for p in fp_control):
            print(f"    ! {p}")
    print(f"\n  Report: {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())