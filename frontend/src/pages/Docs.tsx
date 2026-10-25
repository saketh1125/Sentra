import { useState } from "react"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

type DocsResult = { status: string; count?: number; docs?: Array<{ chunk_id: string; doc?: { summary?: string; key_behaviors?: string[] }; cached?: boolean; error?: string }>; reason?: string }
type DriftResult = { checked: number; drifted: number; items: Array<{ file_path: string; qualified_name: string; start_line?: number; hash_drift: boolean | null }> }

export default function Docs() {
  const [result, setResult] = useState<DocsResult | null>(null)
  const [drift, setDrift] = useState<DriftResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const repoId = localStorage.getItem("sentra.repoId")

  async function generate() {
    if (!repoId) return
    setBusy(true); setError("")
    try { setResult(await api.post<DocsResult>(`/repos/${repoId}/docs`, { limit: 10, force: false })) }
    catch (e) { setError(e instanceof Error ? e.message : "Documentation generation failed") }
    finally { setBusy(false) }
  }

  async function checkDrift() {
    if (!repoId) return
    setBusy(true); setError("")
    try { setDrift(await api.post<DriftResult>(`/repos/${repoId}/drift`, { threshold: 0.8 })) }
    catch (e) { setError(e instanceof Error ? e.message : "Drift check failed") }
    finally { setBusy(false) }
  }

  if (!repoId) return <Card><CardHeader><CardTitle>Select a repository first</CardTitle><CardDescription>Choose one on the Repos page before generating docs or checking drift.</CardDescription></CardHeader></Card>
  return <div className="grid gap-6">
    <Card><CardHeader><CardTitle>Living documentation</CardTitle><CardDescription>Generate summaries for up to ten source chunks. Mistral receives the selected source code.</CardDescription></CardHeader><CardContent><Button onClick={() => void generate()} disabled={busy}>{busy ? "Working…" : "Generate documentation"}</Button>{result && <p className="mt-3 text-sm">Status: {result.status}{result.count !== undefined ? ` · ${result.count} entries` : ""}{result.reason ? ` · ${result.reason}` : ""}</p>}{result?.docs?.map(d => <div key={d.chunk_id} className="mt-3 rounded-md border p-3"><p className="text-sm">{d.doc?.summary ?? d.error ?? "No summary"}</p>{d.cached && <span className="text-xs text-muted-foreground">Cached</span>}</div>)}</CardContent></Card>
    <Card><CardHeader><CardTitle>Documentation drift</CardTitle><CardDescription>Compare each generated summary’s source hash with the current indexed code.</CardDescription></CardHeader><CardContent><Button variant="outline" onClick={() => void checkDrift()} disabled={busy}>Check drift</Button>{drift && <><p className="mt-3 text-sm">Checked {drift.checked} docs · {drift.drifted} drifted</p>{drift.items.map((d, i) => <div key={`${d.file_path}-${i}`} className="mt-2 rounded-md border p-3 text-sm">{d.file_path} · {d.qualified_name}</div>)}</>}</CardContent></Card>
    {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
  </div>
}
