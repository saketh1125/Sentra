# Sentra Frontend

Vite + React + TypeScript + Tailwind CSS + shadcn/ui.

## Dev

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # production build
```

## Env

Copy `.env.example` to `.env`:

```
VITE_API_URL=http://localhost:8000
```

## Routes

- `/` — Repos
- `/findings` — Findings
- `/pr-risk` — PR Risk
- `/score` — Score

API client: `src/lib/api.ts` (typed fetch, `VITE_API_URL`).
