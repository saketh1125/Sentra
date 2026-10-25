from __future__ import annotations

import asyncio
import re
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import Finding, PrAnalysis, Repository

router = APIRouter(prefix="/repos", tags=["pull requests"])


class PrReviewIn(BaseModel):
    pr_url: HttpUrl
    summarize: bool = True


def _github_repo(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http") or parsed.hostname not in ("github.com", "www.github.com"):
        return None
    parts = parsed.path.strip("/").removesuffix(".git").split("/")
    if len(parts) < 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts[:2]):
        return None
    return parts[0], parts[1]


@router.post("/{repo_id}/pr-review")
async def review_pr(repo_id: uuid.UUID, body: PrReviewIn):
    pr = urlparse(str(body.pr_url))
    match = re.fullmatch(r"/([^/]+)/([^/]+)/pull/(\d+)/?", pr.path)
    if pr.hostname not in ("github.com", "www.github.com") or not match:
        raise HTTPException(400, "pr_url must be a GitHub pull request URL")
    owner, name, number_text = match.groups()
    number = int(number_text)

    async with SessionLocal() as session:
        repo = await session.get(Repository, repo_id)
        if repo is None:
            raise HTTPException(404, "repo not found")
        configured_repo = _github_repo(repo.remote_url)
        if not configured_repo or tuple(part.lower() for part in configured_repo) != (owner.lower(), name.lower()):
            raise HTTPException(400, "pull request must belong to this repository")
        findings = (await session.execute(select(Finding).where(Finding.repo_id == repo_id, Finding.status == "open"))).scalars().all()

    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if settings.sentra_gh_token:
        headers["Authorization"] = f"Bearer {settings.sentra_gh_token}"
    api_root = f"https://api.github.com/repos/{owner}/{name}"
    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        response = await client.get(f"{api_root}/pulls/{number}")
        if response.status_code == 404:
            raise HTTPException(404, "pull request not found or inaccessible")
        if response.status_code == 403:
            raise HTTPException(502, "GitHub API rate limit or access denied")
        if response.status_code != 200:
            raise HTTPException(502, f"GitHub API returned HTTP {response.status_code}")
        pr_data = response.json()
        file_response = await client.get(f"{api_root}/pulls/{number}/files", params={"per_page": 100})
        if file_response.status_code != 200:
            raise HTTPException(502, f"GitHub files API returned HTTP {file_response.status_code}")
        files = file_response.json()

    changed = {item.get("filename", "") for item in files if item.get("filename")}
    linked = []
    for finding in findings:
        path = (finding.location or {}).get("path")
        if path in changed:
            linked.append({
                "id": str(finding.id), "module": finding.module,
                "severity": finding.severity, "source": finding.source,
                "path": path, "line": (finding.location or {}).get("start_line"),
                "explanation": finding.explanation,
            })

    patches = []
    for item in files:
        if item.get("patch"):
            patches.append(f"--- {item.get('filename')} ({item.get('status')})\n{item['patch']}")
    diff_context = "\n\n".join(patches)[:18000]
    summary = {
        "text": f"{pr_data.get('title', 'Pull request')} changes {len(files)} files (+{sum(f.get('additions', 0) for f in files)}/-{sum(f.get('deletions', 0) for f in files)} lines).",
        "llm_status": "disabled",
    }

    if body.summarize and diff_context and (settings.mistral_api_key):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "spikes"))
        import _llm
        prompt = (
            "Summarize this GitHub pull request in plain English in 2-4 sentences. "
            "Describe intent and notable changes only; do not invent behavior.\n\n"
            f"Title: {pr_data.get('title', '')}\nDescription: {(pr_data.get('body') or '')[:3000]}\n"
            f"Diff excerpts:\n{diff_context}"
        )
        try:
            summary_text, _, _ = await asyncio.to_thread(
                _llm.chat, messages=[{"role": "user", "content": prompt}], max_tokens=500, temperature=0.1,
            )
            summary = {"text": summary_text, "llm_status": "ok", "model": _llm.default_model()}
        except Exception as exc:
            summary = {**summary, "llm_status": "error", "error": f"{type(exc).__name__}: {exc}"[:240]}

    risk_flags = [
        {"kind": "existing_finding_on_changed_file", **finding}
        for finding in linked
    ]
    result = {
        "number": number,
        "title": pr_data.get("title"),
        "state": pr_data.get("state"),
        "url": pr_data.get("html_url"),
        "head_sha": (pr_data.get("head") or {}).get("sha"),
        "changed_files": [
            {"path": f.get("filename"), "status": f.get("status"), "additions": f.get("additions", 0), "deletions": f.get("deletions", 0)}
            for f in files
        ],
        "summary": summary,
        "joined_findings": linked,
        "risk_flags": risk_flags,
    }

    async with SessionLocal() as session:
        record = (await session.execute(
            select(PrAnalysis).where(PrAnalysis.repo_id == repo_id, PrAnalysis.pr_number == number)
            .order_by(PrAnalysis.created_at.desc()).limit(1)
        )).scalars().first()
        if record is None:
            record = PrAnalysis(repo_id=repo_id, pr_number=number)
            session.add(record)
        record.head_sha = result["head_sha"]
        record.findings = risk_flags
        record.summary = summary
        await session.commit()
    return result


@router.get("/{repo_id}/pr-analyses")
async def list_pr_analyses(repo_id: uuid.UUID):
    async with SessionLocal() as session:
        if await session.get(Repository, repo_id) is None:
            raise HTTPException(404, "repo not found")
        rows = (await session.execute(
            select(PrAnalysis).where(PrAnalysis.repo_id == repo_id)
            .order_by(PrAnalysis.created_at.desc())
        )).scalars().all()
        return [{
            "id": str(row.id), "pr_number": row.pr_number, "head_sha": row.head_sha,
            "findings": row.findings, "summary": row.summary,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        } for row in rows]
