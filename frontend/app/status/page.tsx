import type { Metadata } from "next";

import { getPublishedStatus, STATUS_PAGE_URL } from "@/lib/status";

export const metadata: Metadata = { title: "Status | Sunshine Ledger" };

const WINDOW_LABELS: Record<string, string> = { "24h": "Last 24 hours", "7d": "Last 7 days", "30d": "Last 30 days", "90d": "Last 90 days" };

function utc(iso: string | null | undefined): string {
  return iso ? `${iso.slice(0, 16).replace("T", " ")} UTC` : "unknown";
}

/** Uptime as measured from outside our network, with incidents and data freshness.
 *  The same figures are published on a page hosted separately at Amazon Web Services,
 *  which stays up when this site does not. */
export default async function StatusPage() {
  const s = await getPublishedStatus();
  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-2xl font-bold text-ledger-900">Status</h1>
      <p className="mt-2 text-sm text-slate-700">
        Measured from outside our network by Amazon Route 53 health checkers, not by the site itself. The same
        figures are published at <a href={STATUS_PAGE_URL} className="text-sunshine-700 underline">an independent status page</a>{" "}
        that stays up when this site does not.
      </p>
      {!s ? (
        <p className="mt-6 text-sm text-slate-700" role="status">
          The status figures couldn&apos;t be loaded just now. Try the independent status page above.
        </p>
      ) : (
        <>
          <p className="mt-6 text-lg text-ledger-900">
            Now: <strong>{s.current === "up" ? "Up" : s.current === "down" ? "Down" : "Unknown"}</strong>
            <span className="ml-2 text-sm text-slate-500">checked {utc(s.generated_at)}</span>
          </p>
          <h2 className="mt-6 text-base font-semibold text-ledger-900">Uptime</h2>
          <p className="mt-1 text-sm text-slate-700">
            Measured since {utc(s.measured_since)}. Periods with no reading are left out rather than counted as up
            or down; coverage shows how much of each window was measured.
          </p>
          <table className="mt-2 text-sm">
            <thead>
              <tr className="text-left text-slate-500"><th className="pr-6 font-medium">Window</th><th className="pr-6 font-medium">Up</th><th className="font-medium">Coverage</th></tr>
            </thead>
            <tbody>
              {Object.entries(s.windows).map(([k, w]) => (
                <tr key={k}>
                  <td className="pr-6">{WINDOW_LABELS[k] ?? k}</td>
                  <td className="pr-6">{w.uptime_pct === null ? "no data" : `${w.uptime_pct.toFixed(2)}%`}</td>
                  <td>{w.coverage_pct.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h2 className="mt-6 text-base font-semibold text-ledger-900">Incidents</h2>
          {s.incidents.length === 0 ? (
            <p className="mt-1 text-sm text-slate-700">None recorded.</p>
          ) : (
            <ul className="mt-1 space-y-1.5 text-sm text-slate-700">
              {s.incidents.map((i) => (
                <li key={i.start}>
                  {utc(i.start)} to {i.end ? utc(i.end) : "now"} ({i.minutes} min){i.note ? `: ${i.note}` : ""}
                </li>
              ))}
            </ul>
          )}
          <h2 className="mt-6 text-base font-semibold text-ledger-900">Data freshness</h2>
          <p className="mt-1 text-sm text-slate-700">
            {s.data.reachable
              ? `Last data update ${utc(s.data.last_ingest_at)}. ${s.data.sources_fresh} of ${s.data.sources_total} sources checked on schedule.`
              : "The site's data status couldn't be read when these figures were made."}
          </p>
          <p className="mt-6 text-xs text-slate-500">{s.method}</p>
        </>
      )}
    </div>
  );
}
