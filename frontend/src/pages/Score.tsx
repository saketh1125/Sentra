import { Gauge } from "lucide-react"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function Score() {
  return (
    <Card className="mx-auto max-w-lg w-full">
      <CardHeader className="text-center items-center">
        <div className="rounded-full bg-muted p-4 mb-2"><Gauge className="h-8 w-8 text-muted-foreground" /></div>
        <CardTitle>No score yet</CardTitle>
        <CardDescription>Trust score appears after initial scans complete.</CardDescription>
      </CardHeader>
    </Card>
  )
}
