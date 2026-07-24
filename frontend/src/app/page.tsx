import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function DashboardPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Overview placeholder -- wired up to the backend in a later phase.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Watchlist</CardTitle>
            <CardDescription>Companies you&apos;re tracking</CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">No data yet.</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Portfolio</CardTitle>
            <CardDescription>Your declared holdings</CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">No data yet.</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Recent Research</CardTitle>
            <CardDescription>Latest AI-generated reports</CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">No data yet.</CardContent>
        </Card>
      </div>
    </div>
  );
}
