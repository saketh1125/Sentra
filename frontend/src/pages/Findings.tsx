import { ShieldAlert } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function Findings() {
  return (
    <Card className="mx-auto max-w-lg w-full">
      <CardHeader className="text-center items-center">
        <div className="rounded-full bg-muted p-4 mb-2"><ShieldAlert className="h-8 w-8 text-muted-foreground" /></div>
        <CardTitle>No findings yet</CardTitle>
        <CardDescription>Scan a repository to see security findings here.</CardDescription>
      </CardHeader>
      <CardContent className="text-center text-sm text-muted-foreground">Findings will appear after ingestion + scan.</CardContent>
    </Card>
  )
}
