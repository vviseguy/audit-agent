import { api } from "@/lib/api";
import { DraftIssueReview } from "@/components/DraftIssueReview";

export default async function DraftIssuesPage({
  searchParams,
}: {
  searchParams: { project?: string; severity?: string; cwe?: string };
}) {
  const projects = await api.projects().catch(() => []);
  if (!projects.length) {
    return <div className="panel p-6">no projects yet.</div>;
  }

  const selectedId = searchParams.project
    ? Number(searchParams.project)
    : projects[0].id;
  const selected = projects.find((p) => p.id === selectedId) ?? projects[0];
  const drafts = await api.drafts(selected.id).catch(() => []);

  return (
    <DraftIssueReview
      projects={projects}
      initialProjectId={selected.id}
      initialDrafts={drafts}
      initialSeverity={searchParams.severity ?? null}
      initialCwe={searchParams.cwe ?? null}
    />
  );
}
