from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Repository

router = APIRouter(prefix="/repos", tags=["repos"])


class CreateRepoBody(BaseModel):
    remote_url: str
    name: str | None = None
    branch: str = "main"


@router.post("")
async def create_repo(body: CreateRepoBody):
    async with SessionLocal() as session:
        name = body.name or body.remote_url.rstrip("/").split("/")[-1].removesuffix(".git") or "repo"
        repo = Repository(name=name, remote_url=body.remote_url, branch=body.branch, status="pending")
        session.add(repo)
        await session.commit()
        await session.refresh(repo)
        rid = repo.id
    asyncio.create_task(_ingest_background(rid, body.remote_url))
    return {"id": str(rid), "name": name, "remote_url": body.remote_url, "branch": body.branch, "status": "pending"}


async def _ingest_background(repo_id: uuid.UUID, remote_url: str):
    from app.ingest import ingest_repo
    try:
        await ingest_repo(repo_id, remote_url)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("background ingest failed for %s", repo_id)
        try:
            async with SessionLocal() as session:
                r = await session.get(Repository, repo_id)
                if r is not None:
                    r.status = "failed"
                    await session.commit()
        except Exception:
            pass


@router.get("")
async def list_repos():
    async with SessionLocal() as session:
        rows = (await session.execute(select(Repository).order_by(Repository.created_at.desc()))).scalars().all()
        return [{"id": str(r.id), "name": r.name, "remote_url": r.remote_url, "branch": r.branch, "commit_sha": r.commit_sha, "status": r.status, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


@router.get("/{repo_id}")
async def get_repo(repo_id: uuid.UUID):
    async with SessionLocal() as session:
        r = await session.get(Repository, repo_id)
        if r is None:
            raise HTTPException(status_code=404, detail="repo not found")
        return {"id": str(r.id), "name": r.name, "remote_url": r.remote_url, "branch": r.branch, "commit_sha": r.commit_sha, "status": r.status, "created_at": r.created_at.isoformat() if r.created_at else None}


@router.post("/{repo_id}/embed")
async def embed_repo_route(repo_id: uuid.UUID):
    async with SessionLocal() as session:
        r = await session.get(Repository, repo_id)
        if r is None:
            raise HTTPException(status_code=404, detail="repo not found")
    from app.embed import embed_repo as do_embed
    result = await do_embed(repo_id)
    return result


@router.post("/{repo_id}/ingest")
async def retry_ingest(repo_id: uuid.UUID):
    async with SessionLocal() as session:
        repo = await session.get(Repository, repo_id)
        if repo is None:
            raise HTTPException(status_code=404, detail="repo not found")
        repo.status = "pending"
        await session.commit()
        remote_url = repo.remote_url
    asyncio.create_task(_ingest_background(repo_id, remote_url))
    return {"repo_id": str(repo_id), "status": "pending"}
