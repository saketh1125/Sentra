# Data model

The Alembic initial migration creates eight tables. Repository-owned data uses
foreign keys with cascading deletion, so deleting a repository would remove
its files, chunks, embeddings, documents, findings, PR analyses, and score
snapshots.

| Table | Purpose and key data |
|---|---|
| `repositories` | Remote URL, name, branch, current commit SHA, ingest/scan status, creation time. |
| `files` | Repository path, detected language, byte length, and source content hash. |
| `chunks` | File/repository IDs, syntax kind and qualified name, line and byte ranges, content and hash, parent kind, line count, oversized marker. |
| `embeddings` | One vector per chunk, embedding model name, and render mode. Current vector dimension is 384. |
| `documents` | Generated chunk documentation, source hash used for drift checks, generated time, optional document embedding. |
| `findings` | Module, normalized severity, JSON location, scanner source, explanation, open/closed status, stable key, scanner detail, canonical ID. |
| `pr_analyses` | Repository, PR number, head SHA, joined risk findings, summary, and creation time. |
| `score_snapshots` | Repository score, label, per-module breakdown, scoring configuration snapshot, and creation time. |

## Relationships

```text
repositories
├── files ── chunks ── embeddings
│              └────── documents
├── findings
├── pr_analyses
└── score_snapshots
```

Each source `File` belongs to one repository; each `Chunk` belongs to both a
file and repository. Chunk identity anchors embeddings and generated docs.
Findings and PR/score records are repository-scoped.

## Data retention

Database records live in `pgdata`; source checkouts live in `reposdata`; model
downloads live in `modelcache`. `docker compose down` preserves these volumes.
`docker compose down -v` removes them. See [Operations and privacy](OPERATIONS_AND_PRIVACY.md).
