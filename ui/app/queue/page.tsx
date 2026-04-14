import { api } from "@/lib/api";
import { QueueView } from "@/components/QueueView";

export default async function QueuePage() {
  const [availability, forecast, projects] = await Promise.all([
    api.availability().catch(() => ({ cells: [], overrides: [] })),
    api.forecast(undefined, 7).catch(() => ({ windows: [], unscheduled: [] })),
    api.projects().catch(() => []),
  ]);

  return (
    <QueueView
      initialAvailability={availability}
      initialForecast={forecast}
      projects={projects}
    />
  );
}
