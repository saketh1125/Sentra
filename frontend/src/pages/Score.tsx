import { useEffect, useState } from "react"
import { Gauge } from "lucide-react"
import { api } from "@/lib/api"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"

type ScoreData = { score: number; label: string; deduction?: number; breakdown: Record<string, { count: number; deduction: number; cap?: number }> }

export default function Score() {
  const repoId = localStorage.getItem("sentra.repoId")
  const [data, setData] = useState<ScoreData | null>(null)
  const [error, setError] = useState("")
  async function load() {
    if (!repoId) return
    try { setData(await api.get<ScoreData>(`/repos/${repoId}/score`)); setError("") }
    catch (e) { setError(e instanceof Error ? e.message : "Could not load score") }
  }
  useEffect(() => { void load() }, [repoId])
  async function snapshot() {
    if (!repoId) return
    try { await api.post(`/repos/${repoId}/score`, {}); await load() }
    catch (e) { setError(e instanceof Error ? e.message : "Could not save score snapshot") }
  }
  if (!repoId) return <Card><CardHeader><CardTitle>Select a repository first</CardTitle><CardDescription>Choose one on the Repos page to view its readiness score.</CardDescription></CardHeader></Card>
  return <div className="grid gap-4"><div className="flex items-center justify-between"><div><h1 className="text-xl font-semibold">Release readiness</h1><p className="text-sm text-muted-foreground">A deterministic score from open findings.</p></div><Button variant="outline" onClick={() => void snapshot()}>Save snapshot</Button></div>
    {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
    {data && <><Card><CardHeader className="items-center text-center"><div className="mb-2 rounded-full bg-muted p-4"><Gauge className="h-8 w-8 text-primary" /></div><CardTitle className="text-4xl">{data.score}<span className="text-lg text-muted-foreground"> / 100</span></CardTitle><CardDescription>{data.label}</CardDescription></CardHeader></Card>
      <Card><CardHeader><CardTitle>Breakdown</CardTitle></CardHeader><CardContent className="grid gap-3">{Object.entries(data.breakdown).map(([module, row]) => <div key={module} className="flex items-center justify-between border-b pb-2 text-sm"><span>{module.toUpperCase()} · {row.count} findings</span><span>−{row.deduction} points{row.cap ? ` (cap ${row.cap})` : ""}</span></div>)}</CardContent></Card></>}
  </div>
}
