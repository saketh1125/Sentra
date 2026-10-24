from __future__ import annotations
import uuid
from collections import Counter, defaultdict

SEV_WEIGHT = {"critical": 10, "high": 5, "medium": 2, "low": 0.5, "unknown": 0.5}
CAPS = {"m2": 35, "m4": 30, "m5": 15, "m6": 20}
DEFAULT_CAPS = CAPS.copy()

def score_label(s: int) -> str:
    if s >= 85: return "Ready"
    if s >= 60: return "Needs Attention"
    return "At Risk"

def compute_score(findings: list) -> dict:
    by_module = defaultdict(list)
    for f in findings:
        m = getattr(f, "module", None) or (f.get("module") if isinstance(f, dict) else None) or "unknown"
        sev = getattr(f, "severity", None) or (f.get("severity") if isinstance(f, dict) else "low")
        by_module[m].append(sev.lower() if isinstance(sev, str) else "low")
    breakdown = {}
    total_ded = 0
    for mod, cap in CAPS.items():
        sevs = by_module.get(mod, [])
        raw = sum(SEV_WEIGHT.get(s, 0.5) for s in sevs)
        ded = min(raw, cap)
        breakdown[mod] = {"count": len(sevs), "raw": round(raw, 2), "cap": cap, "deduction": round(ded, 2), "by_severity": dict(Counter(sevs))}
        total_ded += ded
    other = [s for m, ss in by_module.items() if m not in CAPS for s in ss]
    if other:
        raw = sum(SEV_WEIGHT.get(s, 0.5) for s in other)
        breakdown["other"] = {"count": len(other), "raw": round(raw, 2), "deduction": round(raw, 2), "by_severity": dict(Counter(other))}
        total_ded += raw
    score = max(0, min(100, round(100 - total_ded)))
    return {"score": score, "label": score_label(score), "deduction": round(total_ded, 2), "breakdown": breakdown, "config_snapshot": {"sev_weight": SEV_WEIGHT, "caps": CAPS}}

async def snapshot_score(repo_id: uuid.UUID, session) -> dict:
    from sqlalchemy import select
    from app.models import Finding, ScoreSnapshot
    rows = (await session.execute(select(Finding).where(Finding.repo_id == repo_id))).scalars().all()
    res = compute_score(rows)
    snap = ScoreSnapshot(repo_id=repo_id, score=res["score"], label=res["label"], breakdown=res["breakdown"], config_snapshot=res["config_snapshot"])
    session.add(snap)
    await session.commit()
    await session.refresh(snap)
    return {"id": str(snap.id), **res, "created_at": snap.created_at.isoformat() if snap.created_at else None}

async def latest_score(repo_id: uuid.UUID, session) -> dict | None:
    from sqlalchemy import select
    from app.models import ScoreSnapshot
    q = select(ScoreSnapshot).where(ScoreSnapshot.repo_id == repo_id).order_by(ScoreSnapshot.created_at.desc()).limit(1)
    row = (await session.execute(q)).scalars().first()
    if not row:
        return None
    return {"id": str(row.id), "repo_id": str(row.repo_id), "score": row.score, "label": row.label, "breakdown": row.breakdown, "config_snapshot": row.config_snapshot, "created_at": row.created_at.isoformat() if row.created_at else None}
