"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { fetchBills, fetchSessions, fetchSourceStatus, fetchStatuses, fetchTags } from "@/lib/api";
import { BROWSE_PAGE_SIZE, buildBrowseQuery, parseBrowseParams, type BrowseFilters } from "@/lib/browse-params";
import { t, tRich } from "@/lib/i18n";
import { jurisdictionOptions } from "@/lib/jurisdictions";
import type { BillListItem, SessionCount, SourceStatus, StatusCount, TagCount } from "@/lib/types";
import BillCard from "@/components/BillCard";
import ElectionContext from "@/components/ElectionContext";
import FollowButton from "@/components/FollowButton";
import DataFreshness from "@/components/DataFreshness";

const PAGE_SIZE = BROWSE_PAGE_SIZE;
const SEARCH_DEBOUNCE_MS = 300;

function BrowsePageInner() {
  const searchParams = useSearchParams();
  const geoFilter = searchParams.get("geo") ?? "";
  const sponsorFilter = searchParams.get("sponsor") ?? "";
  const districtFilter = /^(HD|SD|CD)-\d{3}$/.test(searchParams.get("district") ?? "") ? (searchParams.get("district") as string) : "";
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
      .then((list) => !cancelled && setTags(list))
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
      district: districtFilter || undefined,
      limit: PAGE_SIZE,
      offset,
    })
      .then((res) => {
        if (cancelled) return;
        setBills(res.items);
        setTotal(res.total);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message ?? t("browse.error.fallback"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [urlQ, jurisdiction, status, session, tag, geoFilter, sponsorFilter, districtFilter, offset, reloadKey]);

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
        <h1 className="text-2xl font-bold text-ledger-900">{t("browse.title")}</h1>
        <p className="mt-1 text-sm text-slate-500">
          {t("browse.intro")}
          {geoFilter && (
            <>
              {" "}
              {tRich("browse.filteredGeo", { geo: <span className="font-medium text-ledger-900">{geoFilter}</span> })}
            </>
          )}
          {districtFilter && (
            <>
              {" "}
              {tRich("browse.filteredDistrict", {
                district: <span className="font-medium text-ledger-900">{districtFilter}</span>,
              })}
            </>
          )}
          {sponsorFilter && (
            <>
              {" "}
              {tRich("browse.filteredSponsor", {
                name: (
                  <span className="font-medium text-ledger-900">{sponsorName || t("browse.thisLegislator")}</span>
                ),
              })}
            </>
          )}
        </p>
        <DataFreshness />
      </div>

      <ElectionContext />

      {autoDetected && jurisdiction && (
        <div className="mb-4 flex items-center justify-between rounded-md bg-sunshine-50 px-3 py-2 text-xs text-slate-600">
          <span>
            {t("browse.autoDetected", { place: jurisdiction === "FL" ? t("browse.florida") : jurisdiction })}
          </span>
          <button
            onClick={() => update({ jurisdiction: "" })}
            className="font-medium text-sunshine-700 hover:text-sunshine-800"
          >
            {t("browse.viewAll")}
          </button>
        </div>
      )}

      <div className="mb-6 flex flex-col gap-3 sm:flex-row">
        <input
          type="search"
          aria-label={t("browse.search.label")}
          placeholder={t("browse.search.placeholder")}
          value={qInput}
          onChange={(e) => setQInput(e.target.value)}
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-sunshine-500 focus:outline-none focus:ring-1 focus:ring-sunshine-500"
        />
        <select
          aria-label={t("browse.filter.jurisdiction")}
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
          aria-label={t("browse.filter.status")}
          value={status}
          onChange={(e) => update({ status: e.target.value })}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-sunshine-500 focus:outline-none focus:ring-1 focus:ring-sunshine-500"
        >
          <option value="">{t("browse.all.statuses")}</option>
          {statuses.map((s) => (
            <option key={s.status} value={s.status}>
              {t("browse.option", { label: s.status, count: String(s.count) })}
            </option>
          ))}
        </select>
        <select
          aria-label={t("browse.filter.session")}
          value={session}
          onChange={(e) => update({ session: e.target.value })}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-sunshine-500 focus:outline-none focus:ring-1 focus:ring-sunshine-500"
        >
          <option value="">{t("browse.all.sessions")}</option>
          {sessions.map((s) => (
            <option key={s.session} value={s.session}>
              {t("browse.option", { label: s.session, count: String(s.count) })}
            </option>
          ))}
        </select>
        <select
          aria-label={t("browse.filter.topic")}
          value={tag}
          onChange={(e) => update({ tag: e.target.value })}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-sunshine-500 focus:outline-none focus:ring-1 focus:ring-sunshine-500"
        >
          <option value="">{t("browse.all.topics")}</option>
          {tags.map((tg) => (
            <option key={tg.slug} value={tg.slug}>
              {t("browse.option", { label: tg.label, count: String(tg.count) })}
            </option>
          ))}
        </select>
      </div>

      {tag && (
        <div className="mb-3">
          <FollowButton
            kind="topic"
            target={tag}
            jurisdiction={jurisdiction || ""}
            label={`${tags.find((x) => x.slug === tag)?.label ?? tag}${jurisdiction ? ` · ${jurisdiction}` : ""}`}
          />
        </div>
      )}

      {error && (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <p className="font-medium">{t("browse.error.title")}</p>
          <p className="mt-1">
            {t("browse.error.body")}
          </p>
          <button
            onClick={() => setReloadKey((k) => k + 1)}
            className="mt-3 rounded-md border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-800 hover:bg-red-50"
          >
            {t("browse.retry")}
          </button>
        </div>
      )}

      {!error && loading && <p className="text-sm text-slate-500">{t("browse.loading")}</p>}

      {!error && !loading && bills.length === 0 && (
        <p className="text-sm text-slate-500">{t("browse.empty")}</p>
      )}

      {!error && !loading && bills.length > 0 && (
        <>
          <p className="mb-3 text-xs text-slate-500">
            {t("browse.total", { count: total })}
            {totalPages > 1 && t("browse.pageSuffix", { page: currentPage, pages: totalPages })}
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
                {t("browse.previous")}
              </button>
              <span className="text-xs text-slate-500">
                {t("browse.pageOf", { page: currentPage, pages: totalPages })}
              </span>
              <button
                onClick={() => update({ page: page + 1 })}
                disabled={!hasNext}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {t("browse.next")}
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
    <Suspense fallback={<p className="text-sm text-slate-500">{t("browse.loadingPage")}</p>}>
      <BrowsePageInner />
    </Suspense>
  );
}
