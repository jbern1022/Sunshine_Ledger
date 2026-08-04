"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { fetchBills } from "@/lib/api";
import type { BillListItem } from "@/lib/types";
import BillCard from "@/components/BillCard";

const JURISDICTIONS = [
  { label: "All jurisdictions", value: "" },
  { label: "Florida (state)", value: "FL" },
  { label: "Miami", value: "Miami" },
  { label: "Jacksonville", value: "Jacksonville" },
];

const PAGE_SIZE = 50;

function BrowsePageInner() {
  const searchParams = useSearchParams();
  const geoFilter = searchParams.get("geo") ?? "";

  const [q, setQ] = useState("");
  const [jurisdiction, setJurisdiction] = useState(() => searchParams.get("jurisdiction") ?? "");
  const [autoDetected, setAutoDetected] = useState(() => searchParams.get("auto") === "1");
  const [offset, setOffset] = useState(0);
  const [bills, setBills] = useState<BillListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Any filter change starts back at page 1 -- otherwise you could land on
  // an offset past the end of a newly-narrowed result set.
  useEffect(() => {
    setOffset(0);
  }, [q, jurisdiction, geoFilter]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchBills({ q: q || undefined, jurisdiction_name: jurisdiction || undefined, limit: PAGE_SIZE, offset })
      .then((res) => {
        if (cancelled) return;
        const items = geoFilter
          ? res.items.filter((b) => b.geo_scope_names.some((n) => n.toLowerCase().includes(geoFilter.toLowerCase())))
          : res.items;
        setBills(items);
        setTotal(geoFilter ? items.length : res.total);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message ?? "Failed to load bills. Is the API running?");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [q, jurisdiction, geoFilter, offset]);

  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = Math.max(Math.ceil(total / PAGE_SIZE), 1);
  const hasPrev = offset > 0;
  const hasNext = !geoFilter && offset + PAGE_SIZE < total;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-ledger-900">Tracked bills</h1>
        <p className="mt-1 text-sm text-slate-500">
          Plain-language summaries of Florida state and local legislation. Every summary links to its source.
          {geoFilter && (
            <>
              {" "}
              Filtered to <span className="font-medium text-ledger-900">{geoFilter}</span>.
            </>
          )}
        </p>
      </div>

      {autoDetected && jurisdiction && (
        <div className="mb-4 flex items-center justify-between rounded-md bg-sunshine-50 px-3 py-2 text-xs text-slate-600">
          <span>
            Showing {jurisdiction === "FL" ? "Florida" : jurisdiction} bills based on your location.
          </span>
          <button
            onClick={() => {
              setJurisdiction("");
              setAutoDetected(false);
            }}
            className="font-medium text-sunshine-600 hover:text-sunshine-500"
          >
            View all jurisdictions
          </button>
        </div>
      )}

      <div className="mb-6 flex flex-col gap-3 sm:flex-row">
        <input
          type="search"
          placeholder="Search bill number or title…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-sunshine-500 focus:outline-none focus:ring-1 focus:ring-sunshine-500"
        />
        <select
          value={jurisdiction}
          onChange={(e) => {
            setJurisdiction(e.target.value);
            setAutoDetected(false);
          }}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-sunshine-500 focus:outline-none focus:ring-1 focus:ring-sunshine-500"
        >
          {JURISDICTIONS.map((j) => (
            <option key={j.value} value={j.value}>
              {j.label}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error} — make sure the backend is running (<code>docker compose up</code>) and seeded (
          <code>python -m app.pipeline.seed</code>).
        </div>
      )}

      {!error && loading && <p className="text-sm text-slate-400">Loading bills…</p>}

      {!error && !loading && bills.length === 0 && (
        <p className="text-sm text-slate-400">No bills match your filters.</p>
      )}

      {!error && !loading && bills.length > 0 && (
        <>
          <p className="mb-3 text-xs text-slate-400">
            {total} bill{total === 1 ? "" : "s"}
            {!geoFilter && totalPages > 1 && ` — page ${currentPage} of ${totalPages}`}
          </p>
          <div className="space-y-4">
            {bills.map((bill) => (
              <BillCard key={bill.entity_id} bill={bill} />
            ))}
          </div>

          {!geoFilter && (hasPrev || hasNext) && (
            <div className="mt-6 flex items-center justify-between">
              <button
                onClick={() => setOffset((o) => Math.max(o - PAGE_SIZE, 0))}
                disabled={!hasPrev}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                ← Previous
              </button>
              <span className="text-xs text-slate-400">
                Page {currentPage} of {totalPages}
              </span>
              <button
                onClick={() => setOffset((o) => o + PAGE_SIZE)}
                disabled={!hasNext}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function BrowsePage() {
  return (
    <Suspense fallback={<p className="text-sm text-slate-400">Loading…</p>}>
      <BrowsePageInner />
    </Suspense>
  );
}
