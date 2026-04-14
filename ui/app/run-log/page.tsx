import { api } from "@/lib/api";
import { RunLogView } from "@/components/RunLogView";

export default async function RunLogPage() {
  const [runs, sessions, projects] = await Promise.all([
    api.runs(20).catch(() => []),
    api.sessions().catch(() => []),
    api.projects().catch(() => []),
  ]);

  return (
    <RunLogView initialRuns={runs} sessions={sessions} projects={projects} />
  );
}
