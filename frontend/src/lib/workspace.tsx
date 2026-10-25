import { createContext, useContext, useState, type Dispatch, type ReactNode, type SetStateAction } from "react"

export type Workspace = {
  findings: unknown[]
  score: unknown | null
  prReview: unknown | null
  prAnswer: unknown | null
  prUrl: string
  prQuestion: string
  askResult: unknown | null
  askQuestion: string
  docsResult: unknown | null
  driftResult: unknown | null
}

type WorkspaceContextValue = {
  workspace: Workspace
  setWorkspace: Dispatch<SetStateAction<Workspace>>
}

const initial: Workspace = {
  findings: [], score: null, prReview: null, prAnswer: null, prUrl: "", prQuestion: "",
  askResult: null, askQuestion: "", docsResult: null, driftResult: null,
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null)

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [workspace, setWorkspace] = useState(initial)
  return <WorkspaceContext.Provider value={{ workspace, setWorkspace }}>{children}</WorkspaceContext.Provider>
}

export function useWorkspace() {
  const value = useContext(WorkspaceContext)
  if (!value) throw new Error("useWorkspace must be used within WorkspaceProvider")
  return value
}
