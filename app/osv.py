from __future__ import annotations
import json
import subprocess
import uuid
from pathlib import Path

from sqlalchemy import delete, select

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_REPOS = REPO_ROOT / "data" / "repos"
SCANNER_CANDIDATES = [REPO_ROOT / ".venv" / "bin" / "osv-scanner", Path("/usr/local/bin/osv-scanner"), Path("osv-scanner")]

def _scanner_bin() -> str | None:
    for p in SCANNER_CANDIDATES:
        if Path(p).exists():
            return str(p)
    import shutil
    w = shutil.which("osv-scanner")
    return w

def _repo_path(repo) -> Path:
    from urllib.parse import urlparse
    name = repo.name if getattr(repo, "name", None) else Path(urlparse(repo.remote_url).path).stem or "repo"
    p = DATA_REPOS / name
    if p.exists():
        return p
    for cand in DATA_REPOS.iterdir() if DATA_REPOS.exists() else []:
        if cand.name == name:
            return cand
    return p

def run_osv_scanner(repo_path: Path) -> dict:
    bin_path = _scanner_bin()
    if not bin_path:
        return {"results": [], "_error": "osv-scanner not found"}
    if not repo_path.exists():
        return {"results": [], "_error": f"repo path not found: {repo_path}"}
    cmd = [bin_path, "scan", "source", "--no-ignore", "--format", "json", "-r", str(repo_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        try:
            data = json.loads(proc.stdout) if proc.stdout.strip() else {"results": []}
        except json.JSONDecodeError:
            data = {"results": [], "_stderr": proc.stderr[-1000:]}
        return data
    except Exception as e:
        return {"results": [], "_error": f"{type(e).__name__}: {e}"}

def scan_repo(repo) -> list:
    import sys
    sys.path.insert(0, str(REPO_ROOT / "spikes" / "s3_osv"))
    from normalizer import normalize_scanner_output
    rp = _repo_path(repo)
    data = run_osv_scanner(rp)
    if data.get("_error") or data.get("_stderr"):
        raise RuntimeError(data.get("_error") or data.get("_stderr"))
    return normalize_scanner_output(data, root=str(rp))

async def upsert_osv_findings(repo_id: uuid.UUID, session):
    from app.models import Finding, Repository
    repo = await session.get(Repository, repo_id)
    if not repo:
        return {"error": "repo not found"}
    findings = scan_repo(repo)
    await session.execute(delete(Finding).where(Finding.repo_id == repo_id, Finding.module == "m4"))
    out = []
    for f in findings:
        sev = f.severity if f.severity in ("critical", "high", "medium", "low") else "low"
        stable = f"{repo_id}::{f.canonical_id}::{f.package}@{f.version}"
        loc = {"path": f.lockfile_path}
        detail = {"ecosystem": f.ecosystem, "package": f.package, "version": f.version, "fixed_version": f.fixed_version, "affected_range": f.affected_range, "cvss_vector": f.cvss_vector, "cvss_base_score": f.cvss_base_score, "severity_source": f.severity_source, "advisory_ids": f.advisory_ids, "cve_id": f.cve_id}
        row = Finding(repo_id=repo_id, module="m4", severity=sev, location=loc, source=f.package, explanation=f.summary[:500], status="open", stable_key=stable, detail=detail, canonical_id=f.canonical_id)
        session.add(row)
        out.append({"canonical_id": f.canonical_id, "package": f.package, "version": f.version, "severity": sev, "fixed_version": f.fixed_version})
    await session.commit()
    return {"findings": out, "count": len(out)}
