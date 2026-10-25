# Sentra

Sentra is a local-first repository analysis app. It indexes Python and JavaScript/TypeScript repositories and provides code Q&A with citations, documentation and drift checks, Semgrep findings, OSV dependency findings, and a readiness score.

See [current implementation status](docs/IMPLEMENTATION_STATUS.md) for verified
features and remaining limitations. The older development and session status
documents are historical research checkpoints.

## Run locally

Requirements: Docker Engine with Compose, and Node.js 22+ for the frontend dev server.

1. Copy `.env.example` to `.env` and set `MISTRAL_API_KEY` to enable generated answers and documentation. `SENTRA_GH_TOKEN` is optional and supports private GitHub clones.
2. Start the API and pgvector database:

   ```sh
   docker compose up --build -d
   ```

3. Start the frontend:

   ```sh
   npm --prefix frontend ci
   npm --prefix frontend run dev
   ```

Open the Vite URL (normally `http://localhost:5173`). The API listens only on `127.0.0.1:8000`; health checks are at `/health` and `/ready`.

To manage the backend with a small desktop window instead, run `python3 service_manager.py` from the repository. It can start or stop the Compose services, shows live API/database readiness, and streams Compose output. The frontend dev server is started separately with the command above.

Select a repository after adding its HTTPS Git URL. Sentra clones it, parses supported source files, embeds chunks, and stores the index in Docker volumes. Ask and documentation generation send selected source snippets to Mistral when the key is configured. Without a key, retrieval candidates and citations remain available, while generated text is disabled.

## Analysis sections

- **Ask** searches indexed code and returns cited answers. Retrieved source snippets are sent to Mistral when generation is enabled.
- **Docs & Drift** generates documentation for source chunks and checks whether the indexed code has changed since each document was generated.
- **Findings** lists Semgrep and OSV results. Select a finding to open its location, explanation, and conceptual fix guidance; Sentra does not apply fixes automatically.
- **PR Risk** reviews a GitHub pull request, summarizes its changes, and links changed files to existing findings. After reviewing a PR, use **Ask about this pull request** for questions grounded in the PR metadata and available diff excerpts. GitHub may omit patches for binary files or large changes, and reviews currently inspect up to 100 changed files.
- **Score** explains release readiness with the severity weights, module caps, raw penalties, and deductions applied to the score.

Results and entered Ask/PR text remain available while moving between sections in the current browser session. Mistral may rate-limit requests; when generation is unavailable, review results indicate that no AI answer was returned.

Postgres data, cloned repositories, and model files persist in Docker volumes (`pgdata`, `reposdata`, and `modelcache`). `docker compose down` preserves them; `docker compose down -v` deletes them.

## Backend commands

```sh
docker compose up --build -d
docker compose logs -f api
docker compose down
```

The first build installs pinned Semgrep and OSV-Scanner binaries. The first embedding run downloads the selected BGE model into the persistent model cache.
