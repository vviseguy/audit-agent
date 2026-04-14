import type { Project, ProjectTokenBrief } from "./api";

export type ProjectAlert = {
  kind: "error" | "warn";
  text: string;
};

function parseResult(s: string | null | undefined): any {
  if (!s) return null;
  try {
    return JSON.parse(s);
  } catch {
    return null;
  }
}

function tokenOk(t: ProjectTokenBrief | null | undefined): boolean {
  if (!t) return false;
  const r = parseResult(t.validation_result);
  return r?.ok === true;
}

export function computeProjectAlerts(p: Project): ProjectAlert[] {
  const alerts: ProjectAlert[] = [];
  const read = p.read_token;
  const issues = p.issues_token;

  if (!read) {
    alerts.push({
      kind: "warn",
      text: "No read token linked — only public repos will clone.",
    });
  } else {
    const r = parseResult(read.validation_result);
    if (r && r.ok === false) {
      alerts.push({
        kind: "error",
        text: `Read token "${read.label}" failed pre-flight — likely over-scoped. Swap to a fine-grained read-only PAT.`,
      });
    } else if (!read.validated_at) {
      alerts.push({
        kind: "warn",
        text: `Read token "${read.label}" has never been validated.`,
      });
    }
  }

  if (p.create_issues) {
    if (!issues) {
      alerts.push({
        kind: "warn",
        text:
          "Create issues is on but no issues token is linked. Drafts can still be prepared, but promotion will fail.",
      });
    } else {
      const r = parseResult(issues.validation_result);
      if (r && r.ok === false) {
        alerts.push({
          kind: "error",
          text: `Issues token "${issues.label}" failed pre-flight.`,
        });
      } else if (!issues.validated_at) {
        alerts.push({
          kind: "warn",
          text: `Issues token "${issues.label}" has never been validated.`,
        });
      }
    }
  }

  return alerts;
}

export function worstKind(alerts: ProjectAlert[]): "error" | "warn" | null {
  if (alerts.some((a) => a.kind === "error")) return "error";
  if (alerts.length > 0) return "warn";
  return null;
}

export { tokenOk };
