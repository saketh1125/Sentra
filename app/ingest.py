from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import subprocess
import uuid
from pathlib import Path

from sqlalchemy import select

from app.chunker import EXCLUDE_DIRS, Chunker, ChunkerConfig, language_for_path
from app.db import SessionLocal
from app.models import Chunk as ChunkRow
from app.models import File as FileRow
from app.models import Repository
from app.config import settings

logger = logging.getLogger(__name__)

DATA_REPOS = Path(__file__).resolve().parents[1] / "data" / "repos"


def _repo_dir(name: str) -> Path:
    return DATA_REPOS / name


def _safe_name(remote_url: str, name: str | None) -> str:
    if name:
        if Path(name).name != name or name in (".", ".."):
            raise ValueError("repository name must be a single path component")
        return name
    base = remote_url.rstrip("/").split("/")[-1]
    if base.endswith(".git"):
        base = base[:-4]
    return base or "repo"


def _run_git(args: list[str], cwd: Path | None = None) -> str:
    env = os.environ.copy()
    if settings.sentra_gh_token:
        auth = base64.b64encode(f"x-access-token:{settings.sentra_gh_token}".encode()).decode()
        env.update({
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
            "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {auth}",
            "GIT_TERMINAL_PROMPT": "0",
        })
    r = subprocess.run(
        ["git", *args], cwd=str(cwd) if cwd else None,
        capture_output=True, text=True, timeout=120, env=env,
    )
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr[:500]}")
    return r.stdout.strip()


async def ingest_repo(repo_id: uuid.UUID, remote_url: str) -> dict:
    async with SessionLocal() as session:
        repo = await session.get(Repository, repo_id)
        if repo is None:
            return {"error": "repo_not_found", "repo_id": str(repo_id)}
        name = _safe_name(remote_url, repo.name)
        target = _repo_dir(name)
        target.parent.mkdir(parents=True, exist_ok=True)

        def _clone_or_pull():
            if target.exists() and (target / ".git").exists():
                _run_git(["fetch", "--depth", "1", "origin", repo.branch or "main"], cwd=target)
                try:
                    _run_git(["checkout", repo.branch or "main"], cwd=target)
                except Exception:
                    pass
                _run_git(["reset", "--hard", f"origin/{repo.branch or 'main'}"], cwd=target)
            elif target.exists():
                pass
            else:
                branch = repo.branch or "main"
                try:
                    _run_git(["clone", "--depth", "1", "--branch", branch, remote_url, str(target)])
                except RuntimeError:
                    _run_git(["clone", "--depth", "1", remote_url, str(target)])

        try:
            await asyncio.to_thread(_clone_or_pull)
        except Exception as e:
            repo.status = "failed"
            await session.commit()
            logger.exception("ingest clone failed for %s", repo_id)
            return {"error": str(e)[:500], "repo_id": str(repo_id)}

        try:
            commit_sha = await asyncio.to_thread(lambda: _run_git(["rev-parse", "HEAD"], cwd=target))
        except Exception:
            commit_sha = None

        if commit_sha:
            repo.commit_sha = commit_sha
        repo.status = "ingesting"
        await session.commit()

        def _parse_files():
            chunker = Chunker(ChunkerConfig())
            files: dict[str, tuple[str | None, int, str, list]] = {}
            for path in sorted(target.rglob("*")):
                if not path.is_file() or any(part in EXCLUDE_DIRS for part in path.parts):
                    continue
                language = language_for_path(path)
                if language is None:
                    continue
                try:
                    raw = path.read_bytes()
                    content_hash = hashlib.sha256(raw).hexdigest()
                    chunks, _ = chunker.chunk_file(path, target)
                except (OSError, UnicodeError, ValueError):
                    logger.warning("Skipping unsupported or unreadable source file %s", path)
                    continue
                relative = path.relative_to(target).as_posix()
                files[relative] = (language, len(raw), content_hash, chunks)
            return files

        file_groups = await asyncio.to_thread(_parse_files)

        from collections import defaultdict

        stats = {"files_seen": len(file_groups), "files_upserted": 0, "files_skipped": 0, "files_deleted": 0, "chunks_written": 0, "chunks_deleted": 0}
        existing_files = (await session.execute(select(FileRow).where(FileRow.repo_id == repo_id))).scalars().all()
        by_path: dict[str, FileRow] = {f.path: f for f in existing_files}

        for rel_path, (lang, byte_len, content_hash, chs) in file_groups.items():

            fr = by_path.get(rel_path)
            if fr is not None and fr.content_hash == content_hash:
                stats["files_skipped"] += 1
                continue

            if fr is None:
                fr = FileRow(repo_id=repo_id, path=rel_path, language=lang, byte_len=byte_len, content_hash=content_hash)
                session.add(fr)
                await session.flush()
            else:
                fr.language = lang
                fr.byte_len = byte_len
                fr.content_hash = content_hash
                await session.flush()
                await session.execute(
                    select(ChunkRow).where(ChunkRow.file_id == fr.id)
                )
                from sqlalchemy import delete
                del_res = await session.execute(delete(ChunkRow).where(ChunkRow.file_id == fr.id))
                stats["chunks_deleted"] += del_res.rowcount or 0

            stats["files_upserted"] += 1
            for ch in chs:
                oversized = ch.line_count > 200
                row = ChunkRow(
                    file_id=fr.id,
                    repo_id=repo_id,
                    kind=ch.kind,
                    name=ch.name,
                    qualified_name=ch.qualified_name,
                    start_line=ch.start_line,
                    end_line=ch.end_line,
                    byte_start=ch.byte_start,
                    byte_end=ch.byte_end,
                    content=ch.content,
                    content_hash=ch.content_hash,
                    parent_kind=ch.parent_kind,
                    line_count=ch.line_count,
                    oversized=oversized,
                )
                session.add(row)
                stats["chunks_written"] += 1

        removed_paths = set(by_path) - set(file_groups)
        if removed_paths:
            from sqlalchemy import delete
            removed_ids = [by_path[path].id for path in removed_paths]
            stats["files_deleted"] = len(removed_ids)
            deleted = await session.execute(delete(FileRow).where(FileRow.id.in_(removed_ids)))
            stats["chunks_deleted"] += deleted.rowcount or 0

        repo.status = "embedding"
        await session.commit()
        await session.close()
        from app.embed import embed_repo
        embedding_stats = await embed_repo(repo_id)
        async with SessionLocal() as final_session:
            final_repo = await final_session.get(Repository, repo_id)
            if final_repo is not None:
                final_repo.status = "ready"
                await final_session.commit()
        logger.info("ingest %s done: %s commit=%s", repo_id, stats, commit_sha)
        return {"repo_id": str(repo_id), "commit_sha": commit_sha, **stats, "embedding": embedding_stats}
