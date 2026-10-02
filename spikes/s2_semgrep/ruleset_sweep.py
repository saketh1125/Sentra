"""
Sentra P0 / Spike S2c — Semgrep CE ruleset sweep for decision D9.

S2b measured recall 42.9% on our ground-truth corpus with
p/security-audit + p/python + p/javascript. D9 ("Semgrep rule configuration")
cannot be decided without knowing what a different ruleset buys, and at what
cost in runtime, noise and licence surface.

This sweeps candidate configurations over the SAME corpus so the comparison is
apples-to-apples, and reports recall, control specificity, finding count,
wall-clock and the licence namespaces actually exercised.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections import Counter
from pathlib import Path

import probe as P

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "docs" / "evidence" / "S2c_ruleset_sweep.json"
SEMGREP = REPO_ROOT / ".venv" / "bin" / "semgrep"
PROBE_DIR = REPO_ROOT / "data" / "repos" / "fixtures" / "probe"
CORPUS = REPO_ROOT / "data" / "repos" / "flask"

CANDIDATES: dict[str, list[str]] = {
    "current_p0": ["p/security-audit", "p/python", "p/javascript"],
    "add_secrets": ["p/security-audit", "p/python", "p/javascript", "p/secrets"],
    "add_ci": ["p/security-audit", "p/python", "p/javascript", "p/secrets", "p/ci"],
    "default": ["p/default"],
    "greatest_effort": ["p/greatest-per-language-effort"],
    "owasp_top10": ["p/owasp-top-ten"],
}


def run(rulesets: list[str], target: Path) -> tuple[list[dict], float, list[str]]:
    cmd = [
        str(SEMGREP), "scan", "--json", "--quiet", "--metrics=off",
        "--no-git-ignore", "--timeout", "60",
    ]
    for r in rulesets:
        cmd += ["--config", r]
    cmd.append(str(target))
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    elapsed = time.perf_counter() - t0
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return [], elapsed, [f"unparseable: {proc.stderr[-200:]}"]
    return data.get("results", []), elapsed, data.get("errors", [])


def score(findings: list[dict], truth: list[dict]) -> dict:
    positives = [t for t in truth if t["expect_detected"]]
    negatives = [t for t in truth if not t["expect_detected"]]
    hit: set[str] = set()
    for f in findings:
        path, line = str(Path(f["path"])), f["start"]["line"]
        best, bd = None, 10**9
        for t in truth:
            if not path.endswith(t["file"]):
                continue
            d = abs(line - t["first_line"])
            if d < bd:
                best, bd = t, d
        if best is not None and bd <= 6:
            hit.add(best["pattern_id"])
    tp = [p for p in positives if p["pattern_id"] in hit]
    fn = [p for p in positives if p["pattern_id"] not in hit]
    fp = [p for p in negatives if p["pattern_id"] in hit]
    return {
        "recall": round(len(tp) / max(1, len(positives)), 3),
        "control_specificity": round((len(negatives) - len(fp)) / max(1, len(negatives)), 3),
        "detected": sorted(p["pattern_id"] for p in tp),
        "missed": sorted(p["pattern_id"] for p in fn),
        "controls_flagged": sorted(p["pattern_id"] for p in fp),
    }


def main() -> int:
    truth = P.write_corpus()
    rows = []

    for name, rulesets in CANDIDATES.items():
        findings, elapsed, errors = run(rulesets, PROBE_DIR)
        s = score(findings, truth)
        sev = Counter(f["extra"]["severity"] for f in findings)

        # Cost on a real repository, not just the probe corpus.
        real, real_elapsed, _ = run(rulesets, CORPUS)
        rows.append(
            {
                "rulesets": rulesets,
                "probe_recall": s["recall"],
                "probe_control_specificity": s["control_specificity"],
                "probe_findings": len(findings),
                "probe_detected": s["detected"],
                "probe_missed": s["missed"],
                "controls_flagged": s["controls_flagged"],
                "probe_seconds": round(elapsed, 1),
                "severity_distribution": dict(sev),
                "realrepo_findings": len(real),
                "realrepo_seconds": round(real_elapsed, 1),
                "errors": errors[:2],
            }
        )

    report = {
        "spike": "S2c",
        "subject": "Semgrep CE ruleset comparison for decision D9",
        "toolchain": {"semgrep": "1.179.0"},
        "corpus": "data/repos/fixtures/probe (21 vulnerable patterns, 4 safe controls)",
        "cost_repo": "data/repos/flask (pinned commit)",
        "candidates": rows,
        "note": (
            "Recall is measured against patterns WE authored. It is not a "
            "real-world recall claim and must not be presented as one."
        ),
    }
    OUT.write_text(json.dumps(report, indent=2))

    print("=" * 84)
    print("S2c — SEMGREP RULESET SWEEP (decision D9)")
    print("=" * 84)
    print(f"  {'config':<18} {'recall':>7} {'specif':>7} {'probe#':>7} {'probe s':>8} {'flask#':>7} {'flask s':>8}")
    print("  " + "-" * 80)
    for r in rows:
        print(
            f"  {r['rulesets'][0] if r['rulesets'] else '?':<18} "
            f"{r['probe_recall']:>7.1%} {r['probe_control_specificity']:>7.1%} "
            f"{r['probe_findings']:>7} {r['probe_seconds']:>8.1f} "
            f"{r['realrepo_findings']:>7} {r['realrepo_seconds']:>8.1f}"
        )
    best = max(rows, key=lambda r: (r["probe_recall"], -r["realrepo_seconds"]))
    print("-" * 84)
    print(f"  best recall: {best['rulesets']} @ {best['probe_recall']:.1%}")
    print(f"  still missed by best: {best['probe_missed']}")
    print(f"  Report: {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    raise SystemExit(main())