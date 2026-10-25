import { useState } from "react"
import { GitPullRequest } from "lucide-react"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

type Review = { number: number; title: string; url: string; summary: { text: string; llm_status: string }; changed_files: Array<{ path: string; status: string; additions: number; deletions: number }>; risk_flags: Array<{ severity: string; path: string; line?: number; explanation?: string }> }

export default function PrRisk() {
  const repoId = localStorage.getItem("sentra.repoId")
  const [url, setUrl] = useState("")
  const [review, setReview] = useState<Review | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!repoId) return
    setBusy(true); setError(""); setReview(null)
    try { setReview(await api.post<Review>(`/repos/${repoId}/pr-review`, { pr_url: url, summarize: true })) }
    catch (e) { setError(e instanceof Error ? e.message : "Could not review this pull request") }
    finally { setBusy(false) }
  }
  if (!repoId) return <Card><CardHeader><CardTitle>Select a repository first</CardTitle><CardDescription>Choose one on the Repos page to review its pull requests.</CardDescription></CardHeader></Card>
  return <div className="grid gap-6">
    <Card><CardHeader className="text-center items-center"><div className="rounded-full bg-muted p-4"><GitPullRequest className="h-8 w-8 text-primary" /></div><CardTitle>Pull request risk review</CardTitle><CardDescription>Review a PR from the selected GitHub repository and join changed files to open Sentra findings.</CardDescription></CardHeader><CardContent>
      <form onSubmit={submit} className="flex flex-wrap gap-3"><input required type="url" aria-label="GitHub pull request URL" placeholder="https://github.com/owner/repo/pull/123" value={url} onChange={e => setUrl(e.target.value)} className="min-w-64 flex-1 rounded-md border bg-background px-3 py-2 text-sm" /><Button disabled={busy}>{busy ? "Reviewing…" : "Review PR"}</Button></form>
      <p className="mt-3 text-xs text-muted-foreground">If Mistral is configured, PR diff excerpts are sent to it for a summary. Without Mistral, Sentra returns a deterministic change summary and finding links.</p>
      {error && <p role="alert" className="mt-3 text-sm text-red-600">{error}</p>}
    </CardContent></Card>
    {review && <><Card><CardHeader><CardTitle><a className="underline" href={review.url} target="_blank" rel="noreferrer">#{review.number} · {review.title}</a></CardTitle><CardDescription>{review.changed_files.length} changed files · summary mode: {review.summary.llm_status}</CardDescription></CardHeader><CardContent><p className="whitespace-pre-wrap text-sm leading-6">{review.summary.text}</p><p className="mt-3 text-sm font-medium">{review.risk_flags.length} existing finding(s) on changed files</p>{review.risk_flags.map((f, i) => <div key={`${f.path}-${i}`} className="mt-2 rounded-md border p-3 text-sm"><span className="capitalize">{f.severity}</span> · {f.path}{f.line ? `:${f.line}` : ""}<p className="mt-1 text-muted-foreground">{f.explanation}</p></div>)}</CardContent></Card><Card><CardHeader><CardTitle>Changed files</CardTitle></CardHeader><CardContent className="grid gap-2">{review.changed_files.map(f => <div key={f.path} className="flex flex-wrap justify-between gap-2 text-sm"><span>{f.path}</span><span className="text-muted-foreground">{f.status} · +{f.additions}/−{f.deletions}</span></div>)}</CardContent></Card></>}
  </div>
}
