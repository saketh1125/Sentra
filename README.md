# Sentra

Sentra is a local-first engineering trust tool for understanding whether a
software repository is ready to change or release. It indexes Python and
JavaScript/TypeScript code, answers questions with source citations, generates
code documentation and checks it for drift, runs static and dependency
security scans, reviews GitHub pull requests against existing findings, and
turns open findings into a transparent readiness score.

The backend is FastAPI with PostgreSQL and pgvector. Repository parsing uses
Tree-sitter, retrieval uses local BGE embeddings, Semgrep and OSV-Scanner find
issues, and Mistral optionally generates answers, documentation, and PR
summaries. Sentra provides analysis and conceptual fix guidance; it does not
modify repository files.

## Run locally

Requirements: Docker Engine with Compose, Node.js 22+, and Python 3 with Tkinter
if you want the desktop service manager.

1. Copy `.env.example` to `.env`. Set `MISTRAL_API_KEY` for generated answers,
   docs, and PR summaries. Set `SENTRA_GH_TOKEN` when you need private GitHub
   repository access. Keep `.env` private.
2. Start the API and database:

   ```sh
   docker compose up --build -d
   ```

3. Start the frontend:

   ```sh
   npm --prefix frontend ci
   npm --prefix frontend run dev
   ```

Open the Vite URL, normally `http://localhost:5173`. The API is available at
`http://127.0.0.1:8000`; `/health` and `/ready` report service health. The first
build installs the analysis tools, and the first repository embedding run
downloads the BGE model.

To start or stop the Compose services with a desktop window, run
`python3 service_manager.py`. It shows live API/database readiness and service
command output. Start the frontend separately using the command above.

## Use Sentra

Add a repository using its HTTPS Git URL, wait for indexing to finish, then
select it as active. The **Ask**, **Docs & Drift**, **Findings**, **PR Risk**,
and **Score** sections use that selected repository. Ask and Docs provide code
citations or summaries; Findings opens a detail view with conceptual
remediation guidance; PR Risk accepts a GitHub PR URL and supports follow-up
questions; Score explains severity penalties and module caps. Results remain
available while navigating sections in the current browser session.

Mistral can rate-limit requests. Retrieval results and deterministic PR
metadata remain useful when generated text is unavailable. Mistral calls send
the selected code snippets or PR context needed for the requested operation.

## Documentation

- [Documentation index](docs/README.md)
- [Current implementation status](docs/IMPLEMENTATION_STATUS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API reference](docs/API.md)
- [Data model](docs/DATA_MODEL.md)
- [Scoring model](docs/SCORING.md)
- [Privacy, integrations, and operations](docs/OPERATIONS_AND_PRIVACY.md)
- [Research and architecture decisions](Sentra_research.md) (historical planning record)

PostgreSQL data, cloned repositories, and embedding model files persist in
Docker volumes (`pgdata`, `reposdata`, `modelcache`). `docker compose down`
preserves them; `docker compose down -v` deletes them.
