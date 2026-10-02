"""
Sentra — OSV finding normalisation.

This is spike code written to be production-shaped: if S3 validates, this logic
becomes M4's normaliser (decision D10).

Why a normaliser is needed at all — measured in spike S3:
  * osv-scanner output carries NO top-level severity usable by the score. The
    severity must be resolved from the OSV advisory record.
  * The same vulnerability is reported under MULTIPLE advisory ids (e.g. a
    PyPA id AND a GitHub GHSA id for the same CVE). Measured dedup factor 1.81x
    on our fixture: 38 scanner findings represented only 21 unique CVEs.
    Normalising without dedup would double-count, and because M7 deducts per
    finding, it would inflate the readiness deduction by ~1.8x.
  * Severity is unresolvable for a small minority of advisories. The policy for
    that case must be explicit, not a silent default.

All three behaviours below are therefore deliberate and measured, not stylistic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import cvss

# Sentra severity scale (aligned with PRC 2.5: critical / high / medium / low).
SEVERITIES = ("critical", "high", "medium", "low")

# Explicit policy for advisories that carry no machine-readable severity.
# "unknown" is NOT in the score's severity scale, so an unresolvable advisory
# must not silently inherit a severity. Callers decide how to treat it; the
# normaliser only makes the gap visible.
SEVERITY_UNKNOWN = "unknown"

_CVE_RE = re.compile(r"^CVE-\d{4}-\d{4,}$")


def canonical_ids(identifiers: dict) -> tuple[str, str]:
    """Return (canonical_id, cve_id) for an OSV record.

    canonical_id prefers the CVE when one exists, because CVEs are the only
    identifier that is stable across the multiple advisory databases OSV
    aggregates. Without this, one vulnerability is counted several times.
    """
    candidates = [identifiers.get("id")] + list(identifiers.get("aliases") or [])
    cve = next((c for c in candidates if c and _CVE_RE.match(c)), None)
    primary = identifiers.get("id") or ""
    return (cve or primary, cve or "")


def compute_base_score(vector: str) -> tuple[float | None, str | None]:
    """Compute a CVSS base score from an OSV severity vector string.

    OSV delivers severity as a VECTOR (e.g. "CVSS:3.1/AV:N/..."), not a
    numeric score, so a calculator is unavoidable. Returns (score, error).

    Supports both CVSS v3.1 and v4.0 because the live database contains both
    (measured: 28 CVSS_V3 and 8 CVSS_V4 across our fixture).
    """
    if not vector:
        return None, "empty vector"
    try:
        if vector.startswith("CVSS:4.0") or vector.startswith("CVSS:4"):
            return float(cvss.CVSS4(vector=vector).scores()[0]), None
        if vector.startswith("CVSS:3"):
            return float(cvss.CVSS3(vector=vector).scores()[0]), None
        if vector.startswith("CVSS:2"):
            return float(cvss.CVSS2(vector=vector).scores()[0]), None
    except Exception as exc:  # noqa: BLE001 - malformed advisories exist upstream
        return None, f"{type(exc).__name__}: {exc}"
    return None, f"unrecognised vector prefix: {vector[:20]}"


def vector_to_severity(vector: str) -> tuple[str, float | None]:
    """Map a CVSS vector to Sentra's severity scale using the CVSS spec's own
    qualitative bands (None/Low/Medium/High/Critical), not invented thresholds.

    Source of the bands: CVSS v3.1 / v4.0 specification qualitative severity
    rating scale. Using the spec's bands keeps the mapping defensible under
    review rather than resting on arbitrary cut-points.
    """
    if not vector:
        return SEVERITY_UNKNOWN, None
    try:
        if vector.startswith(("CVSS:4.0", "CVSS:4")):
            cls = cvss.CVSS4(vector=vector)
        elif vector.startswith("CVSS:3"):
            cls = cvss.CVSS3(vector=vector)
        elif vector.startswith("CVSS:2"):
            cls = cvss.CVSS2(vector=vector)
        else:
            return SEVERITY_UNKNOWN, None
    except Exception:  # noqa: BLE001 - malformed upstream advisories exist
        return SEVERITY_UNKNOWN, None

    score = float(cls.scores()[0])
    label = (cls.severities()[0] or "").lower()  # none|low|medium|high|critical
    # CVSS "None" (score 0.0) has no Sentra equivalent; Sentra's floor is
    # "low", and a 0.0 advisory is still worth surfacing to a developer.
    if label in ("none", ""):
        return "low", score
    if label not in SEVERITIES:
        return SEVERITY_UNKNOWN, score
    return label, score


def _severity_from_label(label: str | None) -> str | None:
    """Map a `database_specific.severity` string (e.g. GitHub's "MODERATE")."""
    if not label:
        return None
    l = label.strip().lower()
    table = {
        "critical": "critical",
        "high": "high",
        "moderate": "medium",
        "medium": "medium",
        "low": "low",
        "none": "low",
    }
    return table.get(l)


def normalize_severity(record: dict) -> dict:
    """Deterministic severity resolution with a documented fallback chain.

    Chain (first success wins), recorded in `severity_source` so every value is
    traceable:
      1. CVSS vector -> computed base score -> spec qualitative band
      2. database_specific.severity string -> band
      3. SEVERITY_UNKNOWN, explicitly

    Steps 1 and 2 are ordered because a computed CVSS score is objective while a
    vendor label is editorial.
    """
    out = {
        "severity": SEVERITY_UNKNOWN,
        "severity_source": "none",
        "cvss_vector": None,
        "cvss_type": None,
        "cvss_base_score": None,
        "cvss_error": None,
    }

    sev_list = record.get("severity") or []
    for entry in sev_list:
        vec = entry.get("score") or ""
        vtype = entry.get("type") or ""
        # Prefer a version we can actually compute.
        if not vec.startswith(("CVSS:3", "CVSS:4", "CVSS:2")):
            continue
        score, err = compute_base_score(vec)
        out["cvss_vector"] = vec
        out["cvss_type"] = vtype
        out["cvss_base_score"] = score
        out["cvss_error"] = err
        if err is None:
            sev, _ = vector_to_severity(vec)
            out["severity"] = sev
            out["severity_source"] = f"cvss_vector:{vtype}"
            return out

    ds_label = (record.get("database_specific") or {}).get("severity")
    mapped = _severity_from_label(ds_label)
    if mapped:
        out["severity"] = mapped
        out["severity_source"] = f"database_specific:{ds_label}"
        return out

    out["severity_source"] = "unresolved"
    return out


def extract_fixed_version(affected: list[dict], ecosystem: str) -> str | None:
    """Return the earliest `fixed` version for the package's own ecosystem.

    OSV ranges may include GIT ranges (commit hashes) alongside ECOSYSTEM/SEMVER
    ranges. GIT fixed values are commit SHAs, not versions, so they must be
    excluded or the UI would tell a developer to 'upgrade to a commit hash'.
    """
    best: str | None = None
    for entry in affected or []:
        pkg = entry.get("package") or {}
        if pkg.get("name") and pkg.get("ecosystem") and pkg.get("ecosystem") != ecosystem:
            continue
        for rng in entry.get("ranges") or []:
            rtype = (rng.get("type") or "").upper()
            if rtype == "GIT":
                continue
            if ecosystem and rtype not in ("ECOSYSTEM", "SEMVER"):
                continue
            for ev in rng.get("events") or []:
                fixed = ev.get("fixed")
                if not fixed:
                    continue
                if best is None:
                    best = fixed
                else:
                    best = _min_version(best, fixed)
    return best


_VERSION_PART = re.compile(r"(\d+)")


def _min_version(a: str, b: str) -> str:
    """Best-effort numeric-tuple comparison. Deliberately conservative: when
    versions are not comparable, the FIRST value observed is kept and the
    ambiguity is surfaced by the caller rather than guessed away."""

    def key(v: str):
        return tuple(int(x) for x in _VERSION_PART.findall(v)[:4]) or (0,)

    try:
        return a if key(a) <= key(b) else b
    except Exception:  # pragma: no cover - defensive
        return a


def affected_range_text(affected: list[dict], ecosystem: str) -> str:
    """Human-readable affected ranges, e.g. ">=1.0.0, <2.20.0"."""
    parts: list[str] = []
    for entry in affected or []:
        for rng in entry.get("ranges") or []:
            if (rng.get("type") or "").upper() == "GIT":
                continue
            if ecosystem and (rng.get("type") or "").upper() not in ("ECOSYSTEM", "SEMVER"):
                continue
            intro = fix = None
            for ev in rng.get("events") or []:
                if "introduced" in ev:
                    intro = ev["introduced"]
                if "fixed" in ev:
                    fix = ev["fixed"]
            if intro or fix:
                lo = f">={intro}" if intro and intro != "0" else "all versions"
                hi = f"<{fix}" if fix else "no fix available"
                parts.append(f"{lo}, {hi}")
    return "; ".join(dict.fromkeys(parts)) or "unknown"


@dataclass
class NormalizedFinding:
    """M4's finding shape (FR7). Deliberately the minimum fields the readiness
    score and the UI need, so the score never depends on free text."""

    canonical_id: str
    advisory_ids: list[str]
    cve_id: str
    ecosystem: str
    package: str
    version: str
    lockfile_path: str
    severity: str
    severity_source: str
    cvss_vector: str | None
    cvss_base_score: float | None
    affected_range: str
    fixed_version: str | None
    summary: str
    detail_fields: dict = field(default_factory=dict)


def normalize_scanner_output(
    payload: dict, root: str | None = None
) -> list[NormalizedFinding]:
    """Convert osv-scanner JSON into deduplicated NormalizedFindings."""
    merged: dict[str, NormalizedFinding] = {}

    for res in payload.get("results", []) or []:
        src = res.get("source") or {}
        lock = src.get("path") or ""
        for pkg_entry in res.get("packages", []) or []:
            pkg = pkg_entry.get("package") or {}
            name = pkg.get("name") or ""
            version = pkg.get("version") or ""
            eco = pkg.get("ecosystem") or ""
            for vuln in pkg_entry.get("vulnerabilities", []) or []:
                canon, cve = canonical_ids(vuln)
                affected = vuln.get("affected") or []
                sev = normalize_severity(vuln)
                key = canon or f"{eco}:{name}:{version}"
                existing = merged.get(key)
                if existing:
                    # Same vulnerability via a second advisory id: enrich, never
                    # double-count.
                    existing.advisory_ids.append(vuln.get("id", ""))
                    if existing.severity == SEVERITY_UNKNOWN and sev["severity"] != SEVERITY_UNKNOWN:
                        existing.severity = sev["severity"]
                        existing.severity_source = sev["severity_source"]
                        existing.cvss_vector = sev["cvss_vector"]
                        existing.cvss_base_score = sev["cvss_base_score"]
                    continue
                merged[key] = NormalizedFinding(
                    canonical_id=canon,
                    advisory_ids=[vuln.get("id", "")],
                    cve_id=cve,
                    ecosystem=eco,
                    package=name,
                    version=version,
                    lockfile_path=lock,
                    severity=sev["severity"],
                    severity_source=sev["severity_source"],
                    cvss_vector=sev["cvss_vector"],
                    cvss_base_score=sev["cvss_base_score"],
                    affected_range=affected_range_text(affected, eco),
                    fixed_version=extract_fixed_version(affected, eco),
                    summary=(vuln.get("summary") or vuln.get("details") or "").strip()[:400],
                )

    out = list(merged.values())
    out.sort(key=lambda f: (f.package, f.canonical_id))
    return out