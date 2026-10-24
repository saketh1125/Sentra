import { GitPullRequest } from "lucide-react"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function PrRisk() {
  return (
    <Card className="mx-auto max-w-lg w-full">
      <CardHeader className="text-center items-center">
        <div className="rounded-full bg-muted p-4 mb-2"><GitPullRequest className="h-8 w-8 text-muted-foreground" /></div>
        <CardTitle>No PRs analyzed</CardTitle>
        <CardDescription>Open a pull request to see risk scoring.</CardDescription>
      </CardHeader>
    </Card>
  )
}
