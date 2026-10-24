const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000"

type Health = { status: string }
type Ready = { status: string; db: string }

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

export const api = {
  health: () => get<Health>("/health"),
  ready: () => get<Ready>("/ready"),
  repos: {
    list: () => get<unknown[]>("/repos"),
    create: (body: { url: string }) => post<unknown>("/repos", body),
  },
  get,
  post,
  baseUrl: API_URL,
}
