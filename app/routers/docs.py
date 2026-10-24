from __future__ import annotations
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import Document, Repository

router = APIRouter(prefix="/repos", tags=["docs"])

class DocsIn(BaseModel):
    limit: int = 10
    force: bool = False

@router.post("/{repo_id}/docs")
async def generate_docs(repo_id: uuid.UUID, body: DocsIn):
    async with SessionLocal() as s:
        repo = await s.get(Repository, repo_id)
        if not repo:
            raise HTTPException(404, "repo not found")
    if not settings.mistral_api_key and not __import__("os").environ.get("MISTRAL_API_KEY"):
        return {"status": "disabled", "reason": "MISTRAL_API_KEY not set; docgen is behind feature flag", "model": "ministral-3b-latest"}
    try:
        import sys
        from pathlib import Path
        REPO_ROOT = Path(__file__).resolve().parents[2]
        sys.path.insert(0, str(REPO_ROOT / "spikes"))
        import _llm
        from sqlalchemy import select as sel
        from app.models import Chunk as ChunkRow
        async with SessionLocal() as s2:
            chunks = (await s2.execute(sel(ChunkRow).where(ChunkRow.repo_id == repo_id).limit(body.limit))).scalars().all()
            if not chunks:
                return {"status": "empty", "count": 0}
            out = []
            for c in chunks[: body.limit]:
                prompt = f"Summarize this {c.language or 'code'} unit {c.qualified_name} (lines {c.start_line}-{c.end_line}) in one sentence and list 2-3 key behaviors as JSON with keys summary, key_behaviors, complexity_note.\n\n```\n{c.content[:3000]}\n```"
                try:
                    content, usage, latency = _llm.chat(model="ministral-3b-latest", messages=[{"role": "user", "content": prompt}], max_tokens=600, response_format={"type": "json_object"})
                except Exception as e:
                    msg = str(e)
                    if "429" in msg or "quota" in msg.lower() or "rate" in msg.lower():
                        return {"status": "rate_limited", "error": msg[:300], "generated": len(out), "model": "ministral-3b-latest"}
                    out.append({"chunk_id": str(c.id), "error": msg[:300]})
                    continue
                import json, hashlib
                try:
                    doc = json.loads(content)
                except Exception:
                    doc = {"summary": content[:400], "key_behaviors": [], "complexity_note": ""}
                text = __import__("json").dumps(doc)
                h = hashlib.sha256(text.encode()).hexdigest()
                existing = (await s2.execute(sel(Document).where(Document.chunk_id == c.id))).scalars().first()
                if existing and not body.force:
                    out.append({"chunk_id": str(c.id), "doc": doc, "cached": True})
                else:
                    if existing:
                        existing.text = text
                        existing.source_hash = h
                    else:
                        s2.add(Document(chunk_id=c.id, text=text, source_hash=h))
                    out.append({"chunk_id": str(c.id), "doc": doc, "cached": False})
            await s2.commit()
            return {"status": "ok", "model": "ministral-3b-latest", "count": len(out), "docs": out}
    except HTTPException:
        raise
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"[:500], "model": "ministral-3b-latest"}
