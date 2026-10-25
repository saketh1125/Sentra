# API reference

Base URL for local development: `http://127.0.0.1:8000`. JSON request and
response bodies are used unless stated otherwise. Repository identifiers are
UUIDs. The running OpenAPI schema is available at `/openapi.json`.

## Health

| Method and path | Description |
|---|---|
| `GET /health` | Process health. Returns `{"status":"ok"}`. |
| `GET /ready` | Database readiness. Returns `ready` when `SELECT 1` succeeds. |

## Repositories

| Method and path | Description |
|---|---|
| `POST /repos` | Register and asynchronously ingest a repository. Body: `remote_url`, optional `name`, optional `branch` (defaults to `main`). |
| `GET /repos` | List repositories and their ingest status. |
| `GET /repos/{repo_id}` | Get repository metadata. |
| `POST /repos/{repo_id}/ingest` | Retry clone/update, parsing, and embedding. |
| `POST /repos/{repo_id}/embed` | Embed any unembedded chunks. |

Repository status commonly moves through `pending`, `ingesting`, `embedding`,
and `ready`; failures use `failed`. Scan failures use `scan_failed`.

## Retrieval and documentation

| Method and path | Description |
|---|---|
| `POST /repos/{repo_id}/ask` | Body: `question`, optional `top_k` (clamped to 1–20). Returns answer (when generated), retrieval candidates, and citations. |
| `POST /repos/{repo_id}/docs` | Body: optional `limit` (default 10) and `force` (default false). Generates or reuses chunk documentation. |
| `POST /repos/{repo_id}/drift` | Body: optional `threshold` (default 0.8). Checks documented chunks for source-hash and supported AST-fingerprint drift. |

Ask returns ranked source candidates even when model generation is unavailable.
The candidates include source content; clients should treat them as code data.
Docs results can contain `ok`, `empty`, `disabled`, `rate_limited`, or `error`
status values.

Drift currently compares stored source hashes and AST fingerprints. The API
accepts a threshold for the future embedding-similarity branch, but does not
currently persist/use reference embeddings for this route, so changing the
threshold alone does not change current hash/AST results.

## Scanning, findings, and score

| Method and path | Description |
|---|---|
| `POST /repos/{repo_id}/scan` | Starts requested scanner modules (`m2` for Semgrep, `m4` for OSV); defaults to both. Returns while scan runs in a background task. |
| `GET /repos/{repo_id}/findings` | List findings. Optional `module` and `severity` filters. |
| `GET /repos/{repo_id}/score` | Return the latest saved score snapshot, or compute the current score from findings. |
| `POST /repos/{repo_id}/score` | Calculate and persist a score snapshot. |

## Pull requests

| Method and path | Description |
|---|---|
| `POST /repos/{repo_id}/pr-review` | Body: `pr_url`, optional `summarize` (default true). Fetches GitHub PR metadata/files, joins changed paths to open findings, and saves the review. Currently reads at most 100 changed files. |
| `POST /repos/{repo_id}/pr-review/{pr_number}/ask` | Body: `question` (1–2000 characters). Fetches PR context and returns a grounded Mistral answer when configured. Review the PR first. |
| `GET /repos/{repo_id}/pr-analyses` | List saved PR analyses. |

PR Q&A uses PR metadata and available diff patches; GitHub may omit patches for
large or binary files. A missing answer can indicate Mistral rate limiting.
