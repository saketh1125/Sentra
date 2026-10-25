from __future__ import annotations
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Finding, Repository

router = APIRouter(prefix="/repos", tags=["scan", "findings", "score", "drift"])

class ScanIn(BaseModel):
    modules: Optional[list[str]] = None

@router.post("/{repo_id}/scan")
async def trigger_scan(repo_id: uuid.UUID, body: ScanIn, bg: BackgroundTasks):
    async with SessionLocal() as s:
        repo = await s.get(Repository, repo_id)
        if not repo:
            raise HTTPException(404, "repo not found")
    mods = body.modules or ["m4", "m2"]
    mods = [m for m in mods if m in ("m4", "m2")]
    if not mods:
        raise HTTPException(400, "modules must include m2 and/or m4")

    async with SessionLocal() as s:
        repo = await s.get(Repository, repo_id)
        repo.status = "scanning"
        await s.commit()

    async def _run():
        errors = {}
        try:
            async with SessionLocal() as s2:
                if "m4" in mods:
                    try:
                        from app.osv import upsert_osv_findings
                        result = await upsert_osv_findings(repo_id, s2)
                        if result.get("error"):
                            errors["m4"] = result["error"]
                    except Exception as exc:
                        await s2.rollback()
                        errors["m4"] = f"{type(exc).__name__}: {exc}"[:300]
                if "m2" in mods:
                    try:
                        from app.semgrep import upsert_semgrep_findings
                        result = await upsert_semgrep_findings(repo_id, s2)
                        if result.get("error"):
                            errors["m2"] = result["error"]
                    except Exception as exc:
                        await s2.rollback()
                        errors["m2"] = f"{type(exc).__name__}: {exc}"[:300]
                repo = await s2.get(Repository, repo_id)
                if repo:
                    repo.status = "scan_failed" if errors else "ready"
                    await s2.commit()
        except Exception as exc:
            errors["scan"] = f"{type(exc).__name__}: {exc}"[:300]
            async with SessionLocal() as s3:
                repo = await s3.get(Repository, repo_id)
                if repo:
                    repo.status = "scan_failed"
                    await s3.commit()
        if errors:
            import logging
            logging.getLogger(__name__).error("scan failed for %s: %s", repo_id, errors)

    bg.add_task(_run)
    return {"status": "scanning", "modules": mods}

@router.get("/{repo_id}/findings")
async def list_findings(repo_id: uuid.UUID, module: Optional[str] = None, severity: Optional[str] = None):
    async with SessionLocal() as s:
        repo = await s.get(Repository, repo_id)
        if not repo:
            raise HTTPException(404, "repo not found")
        q = select(Finding).where(Finding.repo_id == repo_id)
        if module:
            q = q.where(Finding.module == module)
        if severity:
            q = q.where(Finding.severity == severity.lower())
        rows = (await s.execute(q)).scalars().all()
        return [{"id": str(r.id), "module": r.module, "severity": r.severity, "location": r.location, "source": r.source, "explanation": r.explanation, "stable_key": r.stable_key, "canonical_id": r.canonical_id, "detail": r.detail, "status": r.status} for r in rows]

@router.get("/{repo_id}/score")
async def get_score(repo_id: uuid.UUID):
    from sqlalchemy import select as sel
    from app.models import ScoreSnapshot
    async with SessionLocal() as s:
        repo = await s.get(Repository, repo_id)
        if not repo:
            raise HTTPException(404, "repo not found")
        snap = (await s.execute(sel(ScoreSnapshot).where(ScoreSnapshot.repo_id == repo_id).order_by(ScoreSnapshot.created_at.desc()).limit(1))).scalars().first()
        if snap:
            return {"id": str(snap.id), "repo_id": str(snap.repo_id), "score": snap.score, "label": snap.label, "breakdown": snap.breakdown, "config_snapshot": snap.config_snapshot, "created_at": snap.created_at.isoformat() if snap.created_at else None}
        from app.score import compute_score
        rows = (await s.execute(sel(Finding).where(Finding.repo_id == repo_id))).scalars().all()
        live = compute_score(rows)
        return {"repo_id": str(repo_id), "score": live["score"], "label": live["label"], "breakdown": live["breakdown"], "config_snapshot": live["config_snapshot"], "snapshot": False}

@router.post("/{repo_id}/score")
async def post_score(repo_id: uuid.UUID):
    async with SessionLocal() as s:
        repo = await s.get(Repository, repo_id)
        if not repo:
            raise HTTPException(404, "repo not found")
        from app.score import snapshot_score
        return await snapshot_score(repo_id, s)

class DriftIn(BaseModel):
    threshold: float = 0.8

@router.post("/{repo_id}/drift")
async def drift(repo_id: uuid.UUID, body: DriftIn):
    async with SessionLocal() as s:
        repo = await s.get(Repository, repo_id)
        if not repo:
            raise HTTPException(404, "repo not found")
        from sqlalchemy import select as sel
        from app.models import Chunk as ChunkRow, Document, File as FileRow
        rows = (await s.execute(
            sel(ChunkRow, FileRow.path, FileRow.language)
            .join(FileRow, ChunkRow.file_id == FileRow.id)
            .where(ChunkRow.repo_id == repo_id)
        )).all()
        docs = (await s.execute(
            sel(Document).join(ChunkRow, Document.chunk_id == ChunkRow.id)
            .where(ChunkRow.repo_id == repo_id)
        )).scalars().all()
        doc_by_chunk = {d.chunk_id: d for d in docs if d.chunk_id}
        from app.drift import drift_check
        out = []
        for c, file_path, language in rows:
            d = doc_by_chunk.get(c.id)
            if not d:
                continue
            r = drift_check(current_text=c.content, reference_hash=d.source_hash, language=language or "python", threshold=body.threshold)
            if r["drift"]:
                out.append({"chunk_id": str(c.id), "file_path": file_path, "qualified_name": c.qualified_name, **{k: v for k, v in r.items() if k not in ("cur_hash", "cur_ast")}, "cur_hash": r["cur_hash"][:12], "cur_ast": (r["cur_ast"] or "")[:12]})
        return {"threshold": body.threshold, "checked": len([c for c, _, _ in rows if c.id in doc_by_chunk]), "drifted": len(out), "items": out[:100]}
