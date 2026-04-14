import { api, type TokenRow, type Vulnerability } from "@/lib/api";
import { ProjectHub } from "@/components/ProjectHub";

export default async function ProjectPage({
  params,
}: {
  params: { id: string };
}) {
  const id = Number(params.id);
  const [project, vulns, tokens] = await Promise.all([
    api.project(id).catch(() => null),
    api.vulnerabilities(id).catch(() => [] as Vulnerability[]),
    api.tokens().catch(() => [] as TokenRow[]),
  ]);

  if (!project) {
    return <div className="panel p-6">Project not found.</div>;
  }

  return (
    <ProjectHub
      initialProject={project}
      vulns={vulns}
      globalTokens={tokens}
    />
  );
}
