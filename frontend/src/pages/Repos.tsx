import { useCallback, useEffect, useState } from "react"
import { FolderGit2, Plus, RefreshCw } from "lucide-react"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

type Repo = { id: string; name: string; remote_url: string; branch: string; commit_sha?: string | null; status: string }

export default function Repos() {
  const [repos, setRepos] = useState<Repo[]>([])
  const [url, setUrl] = useState("")
  const [branch, setBranch] = useState("main")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [activeRepo, setActiveRepo] = useState(() => localStorage.getItem("sentra.repoId") ?? "")

  const refresh = useCallback(async () => {
    try { setRepos(await api.repos.list() as Repo[]); setError("") }
    catch (e) { setError(e instanceof Error ? e.message : "Could not load repositories") }
  }, [])

  useEffect(() => { void refresh() }, [refresh])

  async function addRepo(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setLoading(true); setError("")
    try {
      await api.repos.create({ remote_url: url.trim(), branch: branch.trim() || "main" })
      setUrl(""); await refresh()
    } catch (e) { setError(e instanceof Error ? e.message : "Could not add repository") }
    finally { setLoading(false) }
  }

  return <div className="grid gap-6">
    <Card>
      <CardHeader><CardTitle>Connect a repository</CardTitle><CardDescription>Use a public Git URL, or a private GitHub URL when a token is configured.</CardDescription></CardHeader>
      <CardContent>
        <form className="flex flex-wrap gap-3" onSubmit={addRepo}>
          <input aria-label="Git repository URL" required type="url" placeholder="https://github.com/owner/repository" value={url} onChange={e => setUrl(e.target.value)} className="min-w-64 flex-1 rounded-md border bg-background px-3 py-2 text-sm" />
          <input aria-label="Branch" placeholder="Branch" value={branch} onChange={e => setBranch(e.target.value)} className="w-32 rounded-md border bg-background px-3 py-2 text-sm" />
          <Button type="submit" disabled={loading}><Plus className="mr-2 h-4 w-4" />{loading ? "Adding…" : "Add repository"}</Button>
          <Button type="button" variant="outline" onClick={() => void refresh()} aria-label="Refresh"><RefreshCw className="h-4 w-4" /></Button>
        </form>
        {error && <p role="alert" className="mt-3 text-sm text-red-600">{error}</p>}
      </CardContent>
    </Card>
    {repos.length === 0 ? <Card className="mx-auto w-full max-w-lg">
      <CardHeader className="items-center text-center"><div className="mb-2 rounded-full bg-muted p-4"><FolderGit2 className="h-8 w-8 text-muted-foreground" /></div><CardTitle>No repositories yet</CardTitle><CardDescription>Add a repository above to start analysis.</CardDescription></CardHeader>
    </Card> : <div className="grid gap-3">{repos.map(repo => <Card key={repo.id} className={activeRepo === repo.id ? "border-primary" : ""}><CardContent className="flex flex-wrap items-center gap-3 p-4"><FolderGit2 className="h-5 w-5 text-primary" /><div className="min-w-0 flex-1"><p className="font-medium">{repo.name}</p><p className="truncate text-sm text-muted-foreground">{repo.remote_url} · {repo.branch}</p></div><span className="rounded-full bg-muted px-3 py-1 text-xs">{repo.status}</span>{repo.commit_sha && <code className="text-xs text-muted-foreground">{repo.commit_sha.slice(0, 8)}</code>}<Button variant={activeRepo === repo.id ? "default" : "outline"} onClick={() => { localStorage.setItem("sentra.repoId", repo.id); setActiveRepo(repo.id) }}>{activeRepo === repo.id ? "Active" : "Select"}</Button></CardContent></Card>)}</div>}
  </div>
}
