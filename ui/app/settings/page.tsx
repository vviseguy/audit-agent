import Link from "next/link";
import { api } from "@/lib/api";
import { TokenList } from "@/components/TokenList";

export default async function SettingsPage() {
  const [tokens, config] = await Promise.all([
    api.tokens().catch(() => []),
    api.config().catch(() => null),
  ]);

  return (
    <div className="space-y-6">
      <header>
        <div className="text-xs text-subt">settings</div>
        <h1 className="text-2xl font-semibold tracking-tight">global config</h1>
        <div className="text-subt text-sm mt-1">
          host-level settings. per-project settings live on each{" "}
          <Link className="underline" href="/">
            project page
          </Link>{" "}
          under the settings tab.
        </div>
      </header>

      <section className="panel p-4 space-y-2">
        <h2 className="text-sm font-medium">config.yaml</h2>
        <div className="text-xs text-subt">
          budgets, concurrency, paths, and scheduler — edit on the host then
          restart the server.
        </div>
        {config ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs mt-2">
            {Object.entries(config).map(([section, body]) => (
              <div key={section} className="panel-2 border border-border p-3">
                <div className="text-subt mb-1 uppercase tracking-wider">
                  {section}
                </div>
                <pre className="font-mono whitespace-pre-wrap break-words">
                  {JSON.stringify(body, null, 2)}
                </pre>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-subt text-sm">config unavailable</div>
        )}
      </section>

      <section className="panel p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium">github tokens</h2>
          <div className="text-xs text-subt">
            fine-grained PATs only · pre-flight: read works + write is blocked
          </div>
        </div>
        <TokenList initial={tokens} />
      </section>
    </div>
  );
}
