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
- GitHub PR review joins changed paths with existing findings; private GitHub
  access uses `SENTRA_GH_TOKEN`.

## Current verification

- Docker API and database health checks pass; database migration is applied.
- A public repository was ingested, embedded, and scanned end to end.
- Retrieval and local stubbed generation, documentation, and drift flows were
  exercised without sending source to an external model.
- Frontend production build, Python compile check, Compose config validation,
  and `git diff --check` pass.
- Live Mistral generation and an authenticated GitHub PR fetch have not been
  verified in this session.

## Known limits

- PR review currently reads the first 100 changed files.
- Generated answers, docs, and PR summaries send selected repository context to
  Mistral. Live calls should be made only when the user chooses that feature.
- The API binds to localhost. Docker named volumes persist across `down`; use
  `docker compose down -v` only when intentionally deleting local state.

See [README](../README.md) for setup and [development-status.md](development-status.md)
and [SESSION_PROGRESS.md](SESSION_PROGRESS.md) for historical spike evidence.
