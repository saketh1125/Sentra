import { FolderGit2 } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"

export default function Repos() {
  return (
    <div className="grid gap-6">
      <Card className="mx-auto max-w-lg w-full">
        <CardHeader className="text-center items-center">
          <div className="rounded-full bg-muted p-4 mb-2"><FolderGit2 className="h-8 w-8 text-muted-foreground" /></div>
          <CardTitle>No repositories yet</CardTitle>
          <CardDescription>Connect a GitHub repo to start analysis.</CardDescription>
        </CardHeader>
        <CardContent className="flex justify-center">
          <Button>Add repository</Button>
        </CardContent>
      </Card>
    </div>
  )
}
