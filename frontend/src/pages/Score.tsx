import { useEffect, useState } from "react"
import { Gauge } from "lucide-react"
import { api } from "@/lib/api"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { useWorkspace } from "@/lib/workspace"

type ModuleScore = { count: number; raw: number; deduction: number; cap?: number; by_severity: Record<string, number> }
type ScoreData = { score: number; label: string; deduction?: number; breakdown: Record<string, ModuleScore>; config_snapshot?: { sev_weight?: Record<string, number>; caps?: Record<string, number> }; created_at?: string }
const moduleNames: Record<string, string> = { m2: "Static analysis", m4: "Dependency vulnerabilities", m5: "Pull request risk", m6: "Documentation drift", other: "Other findings" }

export default function Score() {
  const repoId = localStorage.getItem("sentra.repoId")
  const { workspace, setWorkspace } = useWorkspace()
  const data = workspace.score as ScoreData | null
  const [error, setError] = useState("")
  async function load() {
    if (!repoId) return
    try { const score = await api.get<ScoreData>(`/repos/${repoId}/score`); setWorkspace(previous => ({ ...previous, score })); setError("") }
    catch (e) { setError(e instanceof Error ? e.message : "Could not load score") }
  }
  useEffect(() => { void load() }, [repoId])
  async function snapshot() {
    if (!repoId) return
    try { const score = await api.post<ScoreData>(`/repos/${repoId}/score`, {}); setWorkspace(previous => ({ ...previous, score })) }
    catch (e) { setError(e instanceof Error ? e.message : "Could not save score snapshot") }
  }
  if (!repoId) return <Card><CardHeader><CardTitle>Select a repository first</CardTitle><CardDescription>Choose one on the Repos page to view its readiness score.</CardDescription></CardHeader></Card>
  const weights = data?.config_snapshot?.sev_weight ?? { critical: 10, high: 5, medium: 2, low: 0.5, unknown: 0.5 }
  return <div className="grid gap-4"><div className="flex items-center justify-between"><div><h1 className="text-xl font-semibold">Release readiness</h1><p className="text-sm text-muted-foreground">Open finding penalties with explicit severity weights and module caps.</p></div><Button variant="outline" onClick={() => void snapshot()}>Save snapshot</Button></div>
    {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
    {data && <><Card><CardHeader className="items-center text-center"><div className="mb-2 rounded-full bg-muted p-4"><Gauge className="h-8 w-8 text-primary" /></div><CardTitle className="text-4xl">{data.score}<span className="text-lg text-muted-foreground"> / 100</span></CardTitle><CardDescription>{data.label} · {data.deduction ?? Object.values(data.breakdown).reduce((sum, row) => sum + row.deduction, 0)} points deducted</CardDescription></CardHeader></Card>
      <Card><CardHeader><CardTitle>Scoring rules</CardTitle><CardDescription>Each finding contributes by severity. Module deductions stop at that module’s cap.</CardDescription></CardHeader><CardContent><div className="grid grid-cols-2 gap-2 sm:grid-cols-5">{Object.entries(weights).map(([severity, weight]) => <div key={severity} className="rounded-md bg-muted p-3 text-center"><p className="text-xs uppercase text-muted-foreground">{severity}</p><p className="mt-1 font-semibold">−{weight}</p><p className="text-xs text-muted-foreground">points each</p></div>)}</div><p className="mt-4 text-sm">Score = max(0, 100 − sum of capped module deductions), rounded to a whole number.</p></CardContent></Card>
      <Card><CardHeader><CardTitle>Module breakdown</CardTitle><CardDescription>Raw penalties show the uncapped total; applied penalties show what affected the score.</CardDescription></CardHeader><CardContent className="grid gap-4">{Object.entries(data.breakdown).map(([module, row]) => <section key={module} className="rounded-lg border p-4"><div className="flex flex-wrap items-start justify-between gap-2"><div><h3 className="font-semibold">{moduleNames[module] ?? module.toUpperCase()}</h3><p className="mt-1 text-sm text-muted-foreground">{row.count} open finding{row.count === 1 ? "" : "s"}</p></div><div className="text-right text-sm"><p>Raw penalty: {row.raw ?? row.deduction}</p><p>Applied: <strong>−{row.deduction}</strong>{row.cap !== undefined ? ` of ${row.cap} point cap` : ""}</p></div></div>{row.cap !== undefined && <div className="mt-3 h-2 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(100, row.deduction / row.cap * 100)}%` }} /></div>}<div className="mt-3 flex flex-wrap gap-2">{Object.entries(row.by_severity ?? {}).length ? Object.entries(row.by_severity).map(([severity, count]) => <span key={severity} className="rounded-full bg-muted px-3 py-1 text-xs">{count} {severity} × {weights[severity] ?? 0.5} = {count * (weights[severity] ?? 0.5)} pts</span>) : <span className="text-xs text-muted-foreground">No open findings</span>}</div>{row.raw > row.deduction && <p className="mt-3 text-xs text-muted-foreground">The cap reduced this module’s penalty by {(row.raw - row.deduction).toFixed(2)} points.</p>}</section>)}</CardContent></Card>
      {data.created_at && <p className="text-xs text-muted-foreground">Saved snapshot: {new Date(data.created_at).toLocaleString()}</p>}</>}
  </div>
}
