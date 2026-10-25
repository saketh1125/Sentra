# Implementation status

**Updated:** 2026-10-25

Sentra now has a working local backend and frontend. The earlier P0 status and
session notes remain useful as research records, but their statements that
implementation has not started describe an earlier checkpoint. This file is
the current implementation checkpoint.

## Working locally

- FastAPI and pgvector start with `docker compose up --build -d`; `/health` and
  `/ready` report healthy.
- Repository ingestion clones public or token-authorized GitHub repositories,
  parses supported source, creates BGE embeddings, and persists data in named
  Docker volumes.
- Semgrep and OSV scans feed findings and readiness score snapshots.
- Retrieval, cited Q&A, generated documentation, and documentation drift routes
  are connected to the frontend. Mistral generation requires `MISTRAL_API_KEY`.
- GitHub PR review joins changed paths with open findings, summarizes diffs,
  and supports PR-specific Q&A grounded in PR metadata and available patches.
  Private GitHub access uses `SENTRA_GH_TOKEN`.
- The frontend preserves results and entered Ask/PR text across section changes
  during the browser session. Finding details include conceptual fix guidance;
  score details explain weights, caps, and deductions.

## Current verification

- Docker API and database health checks pass; database migration is applied.
- A public repository was ingested, embedded, and scanned end to end.
- Retrieval, live Mistral answer and documentation generation, drift, and live
  GitHub PR review and PR Q&A were exercised. Mistral calls can be rate-limited.
- Frontend production build, Python compile check, Compose config validation,
  and `git diff --check` pass.
- The PR-specific Q&A route was exercised with Mistral against a reviewed PR.
  The frontend production build and Python compile check passed after the
  corresponding changes.

## Known limits

- PR review currently reads the first 100 changed files.
- Generated answers, docs, PR summaries, and PR Q&A send selected repository
  context to Mistral. Mistral rate limits can leave generated text unavailable.
- The API binds to localhost. Docker named volumes persist across `down`; use
  `docker compose down -v` only when intentionally deleting local state.

See [README](../README.md) for setup and [development-status.md](development-status.md)
and [SESSION_PROGRESS.md](SESSION_PROGRESS.md) for historical spike evidence.

Current implementation details are in [Architecture](ARCHITECTURE.md),
[API](API.md), [Data model](DATA_MODEL.md), [Scoring](SCORING.md), and
[Operations and privacy](OPERATIONS_AND_PRIVACY.md).
