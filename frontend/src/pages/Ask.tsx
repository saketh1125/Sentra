import { useState } from "react"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useWorkspace } from "@/lib/workspace"

type Citation = { id: number; file: string; qualified_name: string; start_line: number; end_line: number; score: number }
type Answer = { answer: string | null; citations: Citation[]; model: string; llm_model?: string | null }

export default function Ask() {
  const { workspace, setWorkspace } = useWorkspace()
  const question = workspace.askQuestion
  const result = workspace.askResult as Answer | null
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const repoId = localStorage.getItem("sentra.repoId")

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!repoId) return
    setBusy(true); setError("")
    try { const answer = await api.post<Answer>(`/repos/${repoId}/ask`, { question, top_k: 5 }); setWorkspace(previous => ({ ...previous, askResult: answer })) }
    catch (e) { setError(e instanceof Error ? e.message : "Could not answer this question") }
    finally { setBusy(false) }
  }

  if (!repoId) return <Card><CardHeader><CardTitle>Select a repository first</CardTitle><CardDescription>Choose one on the Repos page, then ask questions about its code.</CardDescription></CardHeader></Card>
  return <div className="grid gap-6">
    <Card><CardHeader><CardTitle>Ask about your code</CardTitle><CardDescription>Answers use retrieved code snippets and include file and line citations.</CardDescription></CardHeader><CardContent>
      <form onSubmit={submit} className="grid gap-3"><textarea required value={question} onChange={e => setWorkspace(previous => ({ ...previous, askQuestion: e.target.value }))} rows={3} placeholder="How does authentication work?" className="w-full rounded-md border bg-background p-3 text-sm" /><Button type="submit" disabled={busy || !question.trim()}>{busy ? "Searching…" : "Ask"}</Button></form>
      <p className="mt-3 text-xs text-muted-foreground">When Mistral is configured, retrieved source snippets are sent to Mistral to draft the answer. Without it, Sentra returns matching code and citations only.</p>
      {error && <p role="alert" className="mt-4 text-sm text-red-600">{error}</p>}
    </CardContent></Card>
    {result && <Card><CardHeader><CardTitle>Answer</CardTitle><CardDescription>{result.llm_model ? `Generated with ${result.llm_model}` : `Retrieved with ${result.model}`}</CardDescription></CardHeader><CardContent className="grid gap-4">
      {result.answer ? <p className="whitespace-pre-wrap leading-7">{result.answer}</p> : <p className="text-sm text-muted-foreground">No generated answer. Review the retrieved code below.</p>}
      <div className="grid gap-2">{result.citations.map(c => <div key={c.id} className="rounded-md border p-3 text-sm"><span className="font-semibold">[{c.id}] {c.file}:{c.start_line}–{c.end_line}</span><span className="ml-2 text-muted-foreground">{c.qualified_name}</span></div>)}</div>
    </CardContent></Card>}
  </div>
}
