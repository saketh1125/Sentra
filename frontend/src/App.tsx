import { useEffect, useState } from "react"
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom"
import { Shield } from "lucide-react"
import { api } from "@/lib/api"
import Findings from "@/pages/Findings"
import PrRisk from "@/pages/PrRisk"
import Repos from "@/pages/Repos"
import Score from "@/pages/Score"
import Ask from "@/pages/Ask"
import Docs from "@/pages/Docs"

const nav = [
  { to: "/", label: "Repos" },
  { to: "/ask", label: "Ask" },
  { to: "/docs", label: "Docs & Drift" },
  { to: "/findings", label: "Findings" },
  { to: "/pr-risk", label: "PR Risk" },
  { to: "/score", label: "Score" },
]

function HealthBadge() {
  const [status, setStatus] = useState<string>("…")
  useEffect(() => { api.health().then(r => setStatus(r.status)).catch(() => setStatus("offline")) }, [])
  const color = status === "ok" ? "bg-emerald-500" : status === "offline" ? "bg-red-500" : "bg-amber-500"
  return <span className="flex items-center gap-1.5 text-xs text-muted-foreground"><span className={`h-2 w-2 rounded-full ${color}`} />{status}</span>
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-background">
        <header className="sticky top-0 z-10 border-b bg-card/80 backdrop-blur">
          <div className="mx-auto max-w-6xl flex h-14 items-center gap-6 px-4">
            <span className="flex items-center gap-2 font-semibold"><Shield className="h-5 w-5 text-primary" />Sentra</span>
            <nav className="flex gap-1">
              {nav.map(n => (
                <NavLink key={n.to} to={n.to} className={({ isActive }) => `rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${isActive ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground"}`}>{n.label}</NavLink>
              ))}
            </nav>
            <div className="ml-auto"><HealthBadge /></div>
          </div>
        </header>
        <main className="mx-auto max-w-6xl p-6">
          <Routes>
            <Route path="/" element={<Repos />} />
            <Route path="/ask" element={<Ask />} />
            <Route path="/docs" element={<Docs />} />
            <Route path="/findings" element={<Findings />} />
            <Route path="/pr-risk" element={<PrRisk />} />
            <Route path="/score" element={<Score />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
