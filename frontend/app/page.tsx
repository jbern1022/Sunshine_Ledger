"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { fetchBills, fetchSessions, fetchSourceStatus, fetchStatuses, fetchTags } from "@/lib/api";
import { BROWSE_PAGE_SIZE, buildBrowseQuery, parseBrowseParams, type BrowseFilters } from "@/lib/browse-params";
import { jurisdictionOptions } from "@/lib/jurisdictions";
import type { BillListItem, SessionCount, SourceStatus, StatusCount, TagCount } from "@/lib/types";
import BillCard from "@/components/BillCard";
import ElectionContext from "@/components/ElectionContext";
import DataFreshness from "@/components/DataFreshness";

const PAGE_SIZE = BROWSE_PAGE_SIZE;
const SEARCH_DEBOUNCE_MS = 300;

function BrowsePageInner() {
  const searchParams = useSearchParams();
  const geoFilter = searchParams.get("geo") ?? "";
  const sponsorFilter = searchParams.get("sponsor") ?? "";
  const sponsorName = searchParams.get("sponsorName") ?? "";

  // Filters and the page live in the URL (lib/browse-params): the view can be
  // shared, and back/forward walk through filter changes.
  const router = useRouter();
  const pathname = usePathname();
  const { q: urlQ, jurisdiction, status, session, tag, page } = parseBrowseParams(searchParams);
  const autoDetected = searchParams.get("auto") === "1";
  const offset = (page - 1) * PAGE_SIZE;

  const update = (patch: Partial<BrowseFilters>, replace = false) => {
    const qs = buildBrowseQuery(new URLSearchParams(searchParams.toString()), patch);
    const url = qs ? `${pathname}?${qs}` : pathname;
    if (replace) router.replace(url, { scroll: false });
    else router.push(url, { scroll: false });
  };

  // The search box keeps its own text while typing; the URL follows after a
  // pause (replace, so each keystroke isn't a history entry).
  const [qInput, setQInput] = useState(urlQ);
  const latest = useRef({ qInput, urlQ, update });
  latest.current = { qInput, urlQ, update };

  useEffect(() => {
    setQInput(urlQ); // back/forward or a shared link changed the URL
  }, [urlQ]);

  useEffect(() => {
    const timer = setTimeout(() => {
      const { qInput: typed, urlQ: inUrl, update: apply } = latest.current;
      if (typed !== inUrl) apply({ q: typed }, true);
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [qInput]);

  const [statuses, setStatuses] = useState<StatusCount[]>([]);
  const [sessions, setSessions] = useState<SessionCount[]>([]);
  const [tags, setTags] = useState<TagCount[]>([]);
  const [sourceStatuses, setSourceStatuses] = useState<SourceStatus[] | null>(null);
  const [bills, setBills] = useState<BillListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  // The jurisdiction dropdown lists the cities the site actually ingests; if
  // the list can't be fetched it falls back to the known cities.
  useEffect(() => {
    let cancelled = false;
    fetchSourceStatus()
      .then((s) => !cancelled && setSourceStatuses(s))
      .catch(() => !cancelled && setSourceStatuses(null));
    return () => {
      cancelled = true;
    };
  }, []);

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

  // State bill numbers repeat every session (HB 117 exists in 2024, 2025 and
  // 2026), so sessions are a filter too, scoped like statuses.
  useEffect(() => {
    let cancelled = false;
    fetchSessions(jurisdiction || undefined)
      .then((s) => !cancelled && setSessions(s))
      .catch(() => !cancelled && setSessions([]));
    return () => {
      cancelled = true;
    };
  }, [jurisdiction]);

  useEffect(() => {
    if (session && sessions.length > 0 && !sessions.some((s) => s.session === session)) {
      update({ session: "" }, true);
    }
  }, [sessions, session]); // eslint-disable-line react-hooks/exhaustive-deps

  // A status that doesn't exist in the newly-chosen jurisdiction would
  // silently return nothing, so drop it rather than leave a dead filter on.
  useEffect(() => {
    if (status && statuses.length > 0 && !statuses.some((s) => s.status === status)) {
      update({ status: "" }, true);
    }
  }, [statuses, status]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchBills({
      q: urlQ || undefined,
      jurisdiction_name: jurisdiction || undefined,
      status: status || undefined,
      session: session || undefined,
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
        if (!cancelled) setError(err.message ?? "Failed to load bills.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [urlQ, jurisdiction, status, session, tag, geoFilter, sponsorFilter, offset, reloadKey]);

  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = Math.max(Math.ceil(total / PAGE_SIZE), 1);

  // A shared or stale link can name a page past the end of the results (the
  // list shrank, or ?page=999 was typed). Rather than say no bills match when
  // some do, go to the last page that exists.
  useEffect(() => {
    if (!loading && !error && total > 0 && offset >= total) update({ page: totalPages }, true);
  }, [loading, error, total, offset, totalPages]); // eslint-disable-line react-hooks/exhaustive-deps

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
        <DataFreshness />
      </div>

      <ElectionContext />

      {autoDetected && jurisdiction && (
        <div className="mb-4 flex items-center justify-between rounded-md bg-sunshine-50 px-3 py-2 text-xs text-slate-600">
          <span>
            Showing {jurisdiction === "FL" ? "Florida" : jurisdiction} bills based on your location.
          </span>
          <button
            onClick={() => update({ jurisdiction: "" })}
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
          value={qInput}
          onChange={(e) => setQInput(e.target.value)}
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-sunshine-500 focus:outline-none focus:ring-1 focus:ring-sunshine-500"
        />
        <select
          aria-label="Filter by jurisdiction"
          value={jurisdiction}
          onChange={(e) => update({ jurisdiction: e.target.value })}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-sunshine-500 focus:outline-none focus:ring-1 focus:ring-sunshine-500"
        >
          {jurisdictionOptions(sourceStatuses).map((j) => (
            <option key={j.value} value={j.value}>
              {j.label}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by status"
          value={status}
          onChange={(e) => update({ status: e.target.value })}
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
          aria-label="Filter by session"
          value={session}
          onChange={(e) => update({ session: e.target.value })}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-sunshine-500 focus:outline-none focus:ring-1 focus:ring-sunshine-500"
        >
          <option value="">All sessions</option>
          {sessions.map((s) => (
            <option key={s.session} value={s.session}>
              {s.session} ({s.count})
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by topic"
          value={tag}
          onChange={(e) => update({ tag: e.target.value })}
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
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <p className="font-medium">We couldn&apos;t load bills right now.</p>
          <p className="mt-1">
            The bill service may be restarting or briefly unavailable. Your filters are kept in the address bar, so you
            can retry or come back to this link.
          </p>
          <button
            onClick={() => setReloadKey((k) => k + 1)}
            className="mt-3 rounded-md border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-800 hover:bg-red-50"
          >
            Try again
          </button>
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
                onClick={() => update({ page: page - 1 })}
                disabled={!hasPrev}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                ← Previous
              </button>
              <span className="text-xs text-slate-500">
                Page {currentPage} of {totalPages}
              </span>
              <button
                onClick={() => update({ page: page + 1 })}
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
