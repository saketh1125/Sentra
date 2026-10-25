import { useState } from "react"
import { GitPullRequest } from "lucide-react"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useWorkspace } from "@/lib/workspace"

type Review = { number: number; title: string; url: string; summary: { text: string; llm_status: string }; changed_files: Array<{ path: string; status: string; additions: number; deletions: number }>; risk_flags: Array<{ severity: string; path: string; line?: number; explanation?: string }> }
type PrAnswer = { answer: string | null; model?: string | null; status: string; message?: string }

export default function PrRisk() {
  const repoId = localStorage.getItem("sentra.repoId")
  const { workspace, setWorkspace } = useWorkspace()
  const url = workspace.prUrl
  const review = workspace.prReview as Review | null
  const answer = workspace.prAnswer as PrAnswer | null
  const question = workspace.prQuestion
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!repoId) return
    setBusy(true); setError("")
    try { const next = await api.post<Review>(`/repos/${repoId}/pr-review`, { pr_url: url, summarize: true }); setWorkspace(previous => ({ ...previous, prReview: next, prAnswer: null, prQuestion: "" })) }
    catch (e) { setError(e instanceof Error ? e.message : "Could not review this pull request") }
    finally { setBusy(false) }
  }
  async function askAboutPr(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!repoId || !review || !question.trim()) return
    setBusy(true); setError("")
    try { const next = await api.post<PrAnswer>(`/repos/${repoId}/pr-review/${review.number}/ask`, { question }); setWorkspace(previous => ({ ...previous, prAnswer: next })) }
    catch (e) { setError(e instanceof Error ? e.message : "Could not answer this PR question") }
    finally { setBusy(false) }
  }
  if (!repoId) return <Card><CardHeader><CardTitle>Select a repository first</CardTitle><CardDescription>Choose one on the Repos page to review its pull requests.</CardDescription></CardHeader></Card>
  return <div className="grid gap-6">
    <Card><CardHeader className="text-center items-center"><div className="rounded-full bg-muted p-4"><GitPullRequest className="h-8 w-8 text-primary" /></div><CardTitle>Pull request risk review</CardTitle><CardDescription>Review a PR from the selected GitHub repository and join changed files to open Sentra findings.</CardDescription></CardHeader><CardContent>
      <form onSubmit={submit} className="flex flex-wrap gap-3"><input required type="url" aria-label="GitHub pull request URL" placeholder="https://github.com/owner/repo/pull/123" value={url} onChange={e => setWorkspace(previous => ({ ...previous, prUrl: e.target.value }))} className="min-w-64 flex-1 rounded-md border bg-background px-3 py-2 text-sm" /><Button disabled={busy}>{busy ? "Reviewing…" : "Review PR"}</Button></form>
      <p className="mt-3 text-xs text-muted-foreground">If Mistral is configured, PR diff excerpts are sent to it for a summary. Without Mistral, Sentra returns a deterministic change summary and finding links.</p>
      {error && <p role="alert" className="mt-3 text-sm text-red-600">{error}</p>}
    </CardContent></Card>
    {review && <><Card><CardHeader><CardTitle><a className="underline" href={review.url} target="_blank" rel="noreferrer">#{review.number} · {review.title}</a></CardTitle><CardDescription>{review.changed_files.length} changed files · summary mode: {review.summary.llm_status}</CardDescription></CardHeader><CardContent><p className="whitespace-pre-wrap text-sm leading-6">{review.summary.text}</p><p className="mt-3 text-sm font-medium">{review.risk_flags.length} existing finding(s) on changed files</p>{review.risk_flags.map((f, i) => <div key={`${f.path}-${i}`} className="mt-2 rounded-md border p-3 text-sm"><span className="capitalize">{f.severity}</span> · {f.path}{f.line ? `:${f.line}` : ""}<p className="mt-1 text-muted-foreground">{f.explanation}</p></div>)}</CardContent></Card>
      <Card><CardHeader><CardTitle>Ask about this pull request</CardTitle><CardDescription>Ask about intent, changed code, or linked findings in PR #{review.number}.</CardDescription></CardHeader><CardContent><form onSubmit={askAboutPr} className="grid gap-3"><textarea required maxLength={2000} rows={3} value={question} onChange={event => setWorkspace(previous => ({ ...previous, prQuestion: event.target.value }))} placeholder="What behavior changes, and are any findings relevant to it?" className="w-full rounded-md border bg-background p-3 text-sm" /><Button type="submit" disabled={busy || !question.trim()}>{busy ? "Thinking…" : "Ask about PR"}</Button></form><p className="mt-3 text-xs text-muted-foreground">The PR metadata and available diff excerpts are sent to Mistral to answer. GitHub may omit diff excerpts for large or binary files.</p>{answer && <div className="mt-4 rounded-lg border bg-muted/40 p-4"><p className="mb-2 text-xs text-muted-foreground">{answer.model ? `Answered with ${answer.model}` : answer.status}</p><p className="whitespace-pre-wrap text-sm leading-6">{answer.answer || answer.message || "No AI answer was returned."}</p></div>}</CardContent></Card>
      <Card><CardHeader><CardTitle>Changed files</CardTitle></CardHeader><CardContent className="grid gap-2">{review.changed_files.map(f => <div key={f.path} className="flex flex-wrap justify-between gap-2 text-sm"><span>{f.path}</span><span className="text-muted-foreground">{f.status} · +{f.additions}/−{f.deletions}</span></div>)}</CardContent></Card></>}
  </div>
}
