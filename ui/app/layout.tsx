import "./globals.css";
import Link from "next/link";
import type { Metadata, Viewport } from "next";
import { BudgetMeter } from "@/components/BudgetMeter";

export const metadata: Metadata = {
  title: "Audit Agent",
  description: "Self-hosted cybersecurity audit agent",
  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = {
  themeColor: "#161b27",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <div className="flex flex-col min-h-screen">
          <header className="border-b border-border bg-panel">
            <div className="max-w-[1400px] mx-auto flex items-center gap-2 px-4 h-14">
              <Link
                href="/"
                className="font-semibold tracking-tight text-ink text-base"
              >
                Audit<span className="text-subt mx-1">·</span>Agent
              </Link>
              <nav className="flex items-center gap-1 ml-6 text-sm">
                <Link className="nav-link" href="/">Projects</Link>
                <Link className="nav-link" href="/queue">Queue</Link>
                <Link className="nav-link" href="/draft-issues">Draft Issues</Link>
                <Link className="nav-link" href="/history">History</Link>
                <Link className="nav-link" href="/jobs">Jobs</Link>
                <Link className="nav-link" href="/run-log">Run Log</Link>
                <Link className="nav-link" href="/settings">Settings</Link>
              </nav>
              <div className="ml-auto">
                <BudgetMeter />
              </div>
            </div>
          </header>
          <main className="flex-1 max-w-[1400px] mx-auto w-full px-4 py-6">
            {children}
          </main>
          <footer className="border-t border-border bg-panel text-subt text-xs py-2 text-center">
            Localhost · runs in Docker · mobile-installable PWA
          </footer>
        </div>
      </body>
    </html>
  );
}
