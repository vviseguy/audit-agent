"use client";

import { useState } from "react";
import { api, type TokenRow } from "@/lib/api";

export function TokenList({ initial }: { initial: TokenRow[] }) {
  const [tokens, setTokens] = useState(initial);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const validate = async (id: number) => {
    setBusyId(id);
    setError(null);
    try {
      const res = await api.validateToken(id);
      setTokens((prev) =>
        prev.map((t) =>
          t.id === id
            ? {
                ...t,
                validated_at: new Date().toISOString(),
                validation_result: JSON.stringify(res),
              }
            : t
        )
      );
    } catch (e: any) {
      setError(`${id}: ${e.message}`);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-2">
      {error && <div className="text-xs text-[#d04a4a]">{error}</div>}
      {tokens.length === 0 ? (
        <div className="text-subt text-sm">
          no github tokens. import a project to seed them.
        </div>
      ) : (
        tokens.map((t) => {
          const last = parseResult(t.validation_result);
          const ok = last?.ok;
          const unlinked = last?.unlinked;
          const identityLogin = last?.identity_login;
          return (
            <div
              key={t.id}
              className="panel-2 border border-border p-3 flex items-start gap-3"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm text-ink">{t.label}</span>
                  <span className="text-xs text-subt font-mono">
                    {t.scope}
                  </span>
                  {ok === true && !unlinked && (
                    <span className="text-xs text-[#4fae7a]">✓ Validated</span>
                  )}
                  {ok === true && unlinked && (
                    <span
                      className="text-xs text-[#d4a45c]"
                      title="Identity check passed but no repos are linked yet — bind this token to a project to run full pre-flight."
                    >
                      ◐ Identity OK · no repos linked
                    </span>
                  )}
                  {ok === false && (
                    <span className="text-xs text-[#d04a4a]">
                      ✗ {last?.error ?? "Over-scoped or invalid"}
                    </span>
                  )}
                  {identityLogin && (
                    <span className="text-xs text-subt font-mono">
                      @{identityLogin}
                    </span>
                  )}
                </div>
                <div className="text-xs text-subt mt-1">
                  Projects: {t.projects ?? "—"}
                </div>
                <div className="text-xs font-mono mt-1">
                  {t.validated_at ? (
                    <span className="text-subt">
                      Last checked {new Date(t.validated_at).toLocaleString()}
                    </span>
                  ) : (
                    <span className="text-[#d4a45c]">Never checked</span>
                  )}
                </div>
                {last && last.repos?.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {last.repos.map((r: any, i: number) => (
                      <li
                        key={i}
                        className="text-xs font-mono flex items-center gap-2"
                      >
                        <span
                          style={{
                            color: r.read_ok && r.write_blocked ? "#4fae7a" : "#d04a4a",
                          }}
                        >
                          {r.read_ok && r.write_blocked ? "✓" : "✗"}
                        </span>
                        <span className="text-subt">
                          {r.owner}/{r.name}
                        </span>
                        {!r.read_ok && <span className="text-[#d04a4a]">read failed</span>}
                        {r.read_ok && !r.write_blocked && (
                          <span className="text-[#d04a4a]">WRITE ALLOWED — downgrade PAT</span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <button
                onClick={() => validate(t.id)}
                disabled={busyId === t.id}
                className="panel border border-border hover:bg-panel-2 px-3 py-1 text-xs disabled:opacity-50"
              >
                {busyId === t.id ? "checking…" : "re-validate"}
              </button>
            </div>
          );
        })
      )}
    </div>
  );
}

function parseResult(s: string | null): any {
  if (!s) return null;
  try {
    return JSON.parse(s);
  } catch {
    return null;
  }
}
