import Link from "next/link";
import { api } from "@/lib/api";
import { HistoryFeed } from "@/components/HistoryFeed";

export default async function HistoryPage({
  searchParams,
}: {
  searchParams: { project?: string };
}) {
  const projects = await api.projects().catch(() => []);
  if (!projects.length) {
    return <div className="panel p-6">no projects yet.</div>;
  }

  const selectedId = searchParams.project
    ? Number(searchParams.project)
    : projects[0].id;
  const selected = projects.find((p) => p.id === selectedId) ?? projects[0];

  const entries = await api.projectJournal(selected.id, 500).catch(() => []);

  return (
    <div className="space-y-5">
      <header className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-xs text-subt">history</div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {selected.name}
          </h1>
          <div className="text-subt text-sm mt-1">
            commit-graph-style feed of every agent action across this project.
          </div>
        </div>
        <div className="flex items-center gap-1 flex-wrap text-sm">
          {projects.map((p) => (
            <Link
              key={p.id}
              href={`/history?project=${p.id}`}
              className={
                "px-2 py-1 rounded-sm border " +
                (p.id === selected.id
                  ? "border-border bg-panel-2 text-ink"
                  : "border-transparent text-subt hover:text-ink")
              }
            >
              {p.name}
            </Link>
          ))}
        </div>
      </header>

      <HistoryFeed entries={entries} />
    </div>
  );
}
