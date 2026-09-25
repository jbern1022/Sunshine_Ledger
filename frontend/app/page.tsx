"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { fetchBills, fetchStatuses, fetchTags } from "@/lib/api";
import type { BillListItem, StatusCount, TagCount } from "@/lib/types";
import BillCard from "@/components/BillCard";
import ElectionContext from "@/components/ElectionContext";

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
  const sponsorFilter = searchParams.get("sponsor") ?? "";
  const sponsorName = searchParams.get("sponsorName") ?? "";

  const [q, setQ] = useState("");
  const [jurisdiction, setJurisdiction] = useState(() => searchParams.get("jurisdiction") ?? "");
  const [autoDetected, setAutoDetected] = useState(() => searchParams.get("auto") === "1");
  const [status, setStatus] = useState("");
  const [statuses, setStatuses] = useState<StatusCount[]>([]);
  const [tag, setTag] = useState(() => searchParams.get("tag") ?? "");
  const [tags, setTags] = useState<TagCount[]>([]);
  const [offset, setOffset] = useState(0);
  const [bills, setBills] = useState<BillListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Any filter change starts back at page 1 -- otherwise you could land on
  // an offset past the end of a newly-narrowed result set.
  useEffect(() => {
    setOffset(0);
  }, [q, jurisdiction, status, tag, geoFilter, sponsorFilter]);

  // Tag badges aren't jurisdiction-scoped in the API (unlike statuses), so
  // this fetches once rather than re-running when jurisdiction changes.
  useEffect(() => {
    let cancelled = false;
    fetchTags()
      .then((t) => !cancelled && setTags(t))
      .catch(() => !cancelled && setTags([]));
    return () => {
      cancelled = true;
    };
  }, []);

  // Options follow the jurisdiction filter: showing Jacksonville's
  // municipal statuses while browsing state bills would offer filters that
  // match nothing.
  useEffect(() => {
    let cancelled = false;
    fetchStatuses(jurisdiction || undefined)
      .then((s) => !cancelled && setStatuses(s))
      .catch(() => !cancelled && setStatuses([]));
    return () => {
      cancelled = true;
    };
  }, [jurisdiction]);

  // A status that doesn't exist in the newly-chosen jurisdiction would
  // silently return nothing, so drop it rather than leave a dead filter on.
  useEffect(() => {
    if (status && statuses.length > 0 && !statuses.some((s) => s.status === status)) {
      setStatus("");
    }
  }, [statuses, status]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchBills({
      q: q || undefined,
      jurisdiction_name: jurisdiction || undefined,
      status: status || undefined,
      tag: tag || undefined,
      geo_scope_name: geoFilter || undefined,
      sponsor_entity_id: sponsorFilter || undefined,
      limit: PAGE_SIZE,
      offset,
    })
      .then((res) => {
        if (cancelled) return;
        setBills(res.items);
        setTotal(res.total);
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
  }, [q, jurisdiction, status, tag, geoFilter, sponsorFilter, offset]);

  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = Math.max(Math.ceil(total / PAGE_SIZE), 1);
  const hasPrev = offset > 0;
  const hasNext = offset + PAGE_SIZE < total;

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
          {sponsorFilter && (
            <>
              {" "}
              Filtered to bills sponsored by{" "}
              <span className="font-medium text-ledger-900">{sponsorName || "this legislator"}</span>.
            </>
          )}
        </p>
      </div>

      <ElectionContext />

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
            className="font-medium text-sunshine-700 hover:text-sunshine-800"
          >
            View all jurisdictions
          </button>
        </div>
      )}

      <div className="mb-6 flex flex-col gap-3 sm:flex-row">
        <input
          type="search"
          aria-label="Search bill number or title"
          placeholder="Search bill number or title…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-sunshine-500 focus:outline-none focus:ring-1 focus:ring-sunshine-500"
        />
        <select
          aria-label="Filter by jurisdiction"
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
        <select
          aria-label="Filter by status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-sunshine-500 focus:outline-none focus:ring-1 focus:ring-sunshine-500"
        >
          <option value="">All statuses</option>
          {statuses.map((s) => (
            <option key={s.status} value={s.status}>
              {s.status} ({s.count})
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by topic"
          value={tag}
          onChange={(e) => setTag(e.target.value)}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-sunshine-500 focus:outline-none focus:ring-1 focus:ring-sunshine-500"
        >
          <option value="">All topics</option>
          {tags.map((t) => (
            <option key={t.slug} value={t.slug}>
              {t.label} ({t.count})
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

      {!error && loading && <p className="text-sm text-slate-500">Loading bills…</p>}

      {!error && !loading && bills.length === 0 && (
        <p className="text-sm text-slate-500">No bills match your filters.</p>
      )}

      {!error && !loading && bills.length > 0 && (
        <>
          <p className="mb-3 text-xs text-slate-500">
            {total} bill{total === 1 ? "" : "s"}
            {totalPages > 1 && ` — page ${currentPage} of ${totalPages}`}
          </p>
          <div className="space-y-4">
            {bills.map((bill) => (
              <BillCard key={bill.entity_id} bill={bill} />
            ))}
          </div>

          {(hasPrev || hasNext) && (
            <div className="mt-6 flex items-center justify-between">
              <button
                onClick={() => setOffset((o) => Math.max(o - PAGE_SIZE, 0))}
                disabled={!hasPrev}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                ← Previous
              </button>
              <span className="text-xs text-slate-500">
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
    <Suspense fallback={<p className="text-sm text-slate-500">Loading…</p>}>
      <BrowsePageInner />
    </Suspense>
  );
}
