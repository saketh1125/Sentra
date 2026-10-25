import { useCallback, useEffect, useState } from "react"
import { ShieldAlert } from "lucide-react"
import { api } from "@/lib/api"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"

type Finding = { id: string; module: string; severity: string; source?: string; explanation?: string; location?: { path?: string; start_line?: number; end_line?: number }; detail?: Record<string, unknown> }

export default function Findings() {
  const repoId = localStorage.getItem("sentra.repoId")
  const [items, setItems] = useState<Finding[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const load = useCallback(async () => {
    if (!repoId) return
    try { setItems(await api.get<Finding[]>(`/repos/${repoId}/findings`)); setError("") }
    catch (e) { setError(e instanceof Error ? e.message : "Could not load findings") }
  }, [repoId])
  useEffect(() => { void load() }, [load])

  async function scan() {
    if (!repoId) return
    setBusy(true); setError("")
    try { await api.post(`/repos/${repoId}/scan`, { modules: ["m2", "m4"] }); window.setTimeout(() => void load(), 4000) }
    catch (e) { setError(e instanceof Error ? e.message : "Scan failed") }
    finally { setBusy(false) }
  }

  if (!repoId) return <Card><CardHeader><CardTitle>Select a repository first</CardTitle><CardDescription>Choose one on the Repos page to view findings.</CardDescription></CardHeader></Card>
  return <div className="grid gap-4"><div className="flex items-center justify-between"><div><h1 className="text-xl font-semibold">Findings</h1><p className="text-sm text-muted-foreground">{items.length} stored findings</p></div><div className="flex gap-2"><Button variant="outline" onClick={() => void load()}>Refresh</Button><Button onClick={() => void scan()} disabled={busy}>{busy ? "Starting…" : "Run scans"}</Button></div></div>
    {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
    {items.length === 0 ? <Card><CardHeader className="items-center text-center"><div className="mb-2 rounded-full bg-muted p-4"><ShieldAlert className="h-8 w-8 text-muted-foreground" /></div><CardTitle>No findings yet</CardTitle><CardDescription>Run a scan to check code and dependencies.</CardDescription></CardHeader></Card> : items.map(f => <Card key={f.id}><CardContent className="grid gap-2 p-4"><div className="flex flex-wrap items-center gap-2"><span className="rounded bg-muted px-2 py-1 text-xs uppercase">{f.module}</span><span className="rounded bg-muted px-2 py-1 text-xs capitalize">{f.severity}</span><span className="font-medium">{f.source}</span></div><p className="text-sm">{f.explanation}</p><p className="text-xs text-muted-foreground">{f.location?.path}{f.location?.start_line ? `:${f.location.start_line}${f.location.end_line && f.location.end_line !== f.location.start_line ? `–${f.location.end_line}` : ""}` : ""}</p></CardContent></Card>)}
  </div>
}
