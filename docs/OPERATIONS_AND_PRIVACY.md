# Operations, integrations, and privacy

## Configuration

Copy `.env.example` to `.env` at the repository root. The Compose file passes
these variables to the API container:

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | Compose supplies it | Async PostgreSQL connection. Local host override is available in `.env.example`. |
| `MISTRAL_API_KEY` | Optional | Enables generated code answers, chunk documentation, PR summaries, and PR Q&A. |
| `SENTRA_GH_TOKEN` | Optional | Authenticates private repository clones and GitHub API access. Public GitHub use may work without it. |

Never commit `.env` or include credential values in logs, issue reports, or
documentation. `.env` is excluded by `.gitignore`.

## Network and external data

Repository ingestion retrieves the configured Git remote. Scanning may use
OSV's vulnerability data service. PR review calls the GitHub REST API for the
PR and its changed files.

When Mistral generation is invoked:

- Ask sends the question and selected retrieved source chunks.
- Docs sends selected source chunks for summarization.
- PR summary and PR Q&A send PR metadata plus bounded text diff excerpts (up to
  18,000 characters of diff, with additional title/description/file context).

GitHub may omit textual patches for large or binary files. The codebase and
database otherwise remain local in Docker-managed storage. Review the data
sent to external services before using proprietary code. Mistral API rate
limits can make generated output unavailable; retrieval and deterministic PR
metadata remain separate from generated text.

## Local service operations

```sh
docker compose up --build -d    # build and start API + database
docker compose ps              # inspect service status
docker compose logs -f api     # follow API logs
docker compose stop            # stop without removing containers or data
docker compose down            # stop and remove containers; named volumes persist
docker compose down -v         # also delete all persisted database/repo/model data
```

`python3 service_manager.py` provides a desktop control for starting (`up
--build -d`) or stopping (`stop`) the Compose services. Its live status checks
`GET /ready` and reports API and database readiness. It does not start the
frontend dev server; run `npm --prefix frontend run dev` separately.

The API and database are bound to loopback (`127.0.0.1`). The app currently has
no user authentication and is designed for single-user local development;
do not expose the API port publicly without adding authentication and a
deployment security design.

## Troubleshooting

- API readiness: open `http://127.0.0.1:8000/ready` or inspect `docker compose
  logs -f api`.
- Database: `docker compose ps` should show `db` healthy before API readiness.
- Ingestion: wait for repository status `ready`; if it is `failed`, retry via
  the Repos UI or `POST /repos/{repo_id}/ingest` and inspect API logs.
- Embedding model: the first indexing operation downloads BGE model files into
  `modelcache`, so it can take longer and requires network access.
- Mistral generation: a configured key does not guarantee every request will
  succeed; rate limits may return a status with no generated text.
- Full reset: `docker compose down -v` deletes persisted state and forces a
  fresh repository index and model download.
