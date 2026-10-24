from __future__ import annotations
import json
import subprocess
import uuid
from pathlib import Path

from sqlalchemy import delete, select

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_REPOS = REPO_ROOT / "data" / "repos"
SEMGREP_BIN = REPO_ROOT / ".venv" / "bin" / "semgrep"
SEV_MAP = {"ERROR": "high", "WARNING": "medium", "INFO": "low", "error": "high", "warning": "medium", "info": "low"}
FALLBACK_SEV = "medium"

def _sev(s: str) -> str:
    return SEV_MAP.get(s, SEV_MAP.get(s.upper(), FALLBACK_SEV))

def _repo_path(repo) -> Path:
    from urllib.parse import urlparse
    name = repo.name if getattr(repo, "name", None) else Path(urlparse(repo.remote_url).path).stem or "repo"
    p = DATA_REPOS / name
    if p.exists():
        return p
    if DATA_REPOS.exists():
        for cand in DATA_REPOS.iterdir():
            if cand.name == name:
                return cand
    return p

def run_semgrep(repo_path: Path) -> dict:
    bin_path = str(SEMGREP_BIN) if SEMGREP_BIN.exists() else "semgrep"
    import shutil
    if not Path(bin_path).exists() and not shutil.which("semgrep"):
        return {"results": [], "_error": "semgrep not found"}
    cmd = [bin_path, "scan", "--json", "--quiet", "--metrics=off", "--no-git-ignore", "--timeout", "60", "--config", "p/default", str(repo_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        try:
            data = json.loads(proc.stdout) if proc.stdout.strip() else {"results": []}
        except json.JSONDecodeError:
            data = {"results": [], "_stderr": proc.stderr[-1000:]}
        return data
    except Exception as e:
        return {"results": [], "_error": f"{type(e).__name__}: {e}"}

def normalize_semgrep(data: dict, repo_path: Path) -> list[dict]:
    out = []
    for r in data.get("results", []) or []:
        path = r.get("path") or ""
        try:
            rel = str(Path(path).relative_to(repo_path)) if Path(path).is_absolute() else path
        except Exception:
            rel = path
        start = r.get("start") or {}
        end = r.get("end") or {}
        extra = r.get("extra") or {}
        check_id = r.get("check_id") or "unknown"
        sev_raw = extra.get("severity") or "WARNING"
        out.append({
            "path": rel,
            "check_id": check_id,
            "severity": _sev(sev_raw),
            "severity_raw": sev_raw,
            "start_line": start.get("line"),
            "start_col": start.get("col"),
            "start_offset": start.get("offset"),
            "end_line": end.get("line"),
            "end_offset": end.get("offset"),
            "message": (extra.get("message") or "")[:500],
            "fingerprint": extra.get("fingerprint"),
        })
    return out

def scan_repo(repo) -> list[dict]:
    rp = _repo_path(repo)
    data = run_semgrep(rp)
    return normalize_semgrep(data, rp)

async def upsert_semgrep_findings(repo_id: uuid.UUID, session):
    from app.models import Finding, Repository
    repo = await session.get(Repository, repo_id)
    if not repo:
        return {"error": "repo not found"}
    findings = scan_repo(repo)
    await session.execute(delete(Finding).where(Finding.repo_id == repo_id, Finding.module == "m2"))
    out = []
    for f in findings:
        sl = f.get("start_line") or 0; el = f.get("end_line") or sl
        stable = f"{repo_id}::{f['path']}::{f['check_id']}::{sl}-{el}"
        loc = {"path": f["path"], "start_line": sl, "end_line": el, "start_col": f.get("start_col"), "start_offset": f.get("start_offset"), "end_offset": f.get("end_offset")}
        detail = {"check_id": f["check_id"], "severity_raw": f["severity_raw"], "fingerprint": f.get("fingerprint")}
        row = Finding(repo_id=repo_id, module="m2", severity=f["severity"], location=loc, source=f["check_id"], explanation=f["message"], status="open", stable_key=stable, detail=detail, canonical_id=f["check_id"])
        session.add(row)
        out.append({"path": f["path"], "check_id": f["check_id"], "severity": f["severity"], "line": sl})
    await session.commit()
    return {"findings": out, "count": len(out)}
