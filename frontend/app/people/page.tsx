"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchPeople } from "@/lib/api";
import type { PersonListItem } from "@/lib/types";

/** Whoever sponsors tracked bills.
 *
 *  Not titled "Legislators" on purpose: at city level a bill's sponsor is
 *  routinely a committee ("Land Use & Zoning Committee") or an office
 *  ("Mayor") rather than a named person. Those are genuine sponsors in the
 *  official record, so the page shows them -- but calling a committee a
 *  legislator would be wrong.
 *
 *  Ordered by how many bills each is attached to. That ordering is a fact
 *  about the records, not a judgement: sponsoring more bills is neither
 *  good nor bad, and the page says so rather than letting a leaderboard
 *  imply otherwise.
 */
const PAGE_SIZE = 100;

export default function PeoplePage() {
  const [people, setPeople] = useState<PersonListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // A new search starts back at page 1 -- otherwise a narrowed search could
  // land on an offset past the end of the new, smaller result set.
  useEffect(() => {
    setOffset(0);
  }, [q]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchPeople({ q: q || undefined, limit: PAGE_SIZE, offset })
      .then((res) => {
        if (cancelled) return;
        setPeople(res.items);
        setTotal(res.total);
        setError(null);
      })
      .catch(() => !cancelled && setError("Couldn't load legislators."))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [q, offset]);

  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = Math.max(Math.ceil(total / PAGE_SIZE), 1);
  const hasPrev = offset > 0;
  const hasNext = offset + PAGE_SIZE < total;

  return (
    <div>
      <h1 className="text-2xl font-bold text-ledger-900">Sponsors</h1>
      <p className="mt-1 text-sm text-slate-500">
        Whoever sponsors or co-sponsors bills tracked here, with how many they&apos;re attached to.
        At city level a sponsor is often a committee or an office rather than a named person, as
        recorded by the city. Counts describe the record, not performance — filing more bills is
        neither good nor bad, and nothing here rates anyone.
      </p>

      <input
        type="search"
        aria-label="Search sponsors by name or district"
        placeholder="Search by name, committee, or district…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        className="mt-4 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-sunshine-500 focus:outline-none focus:ring-1 focus:ring-sunshine-500"
      />

      {error && <p className="mt-4 text-sm text-red-700">{error}</p>}
      {!error && loading && <p className="mt-4 text-sm text-slate-500">Loading…</p>}
      {!error && !loading && people.length === 0 && (
        <p className="mt-4 text-sm text-slate-500">No sponsors match that search.</p>
      )}

      {!error && !loading && people.length > 0 && (
        <>
          <p className="mt-4 text-xs text-slate-500">
            {total} sponsor{total === 1 ? "" : "s"}
            {totalPages > 1 && ` — page ${currentPage} of ${totalPages}`}
          </p>
          <ul className="mt-2 divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">
            {people.map((p) => (
              <li key={p.entity_id} className="flex items-baseline justify-between gap-3 px-4 py-3">
                <div>
                  <Link
                    href={`/people/${p.entity_id}`}
                    className="text-sm font-medium text-sunshine-700 underline"
                  >
                    {p.name}
                  </Link>
                  <span className="ml-2 text-xs text-slate-500">
                    {[p.role, p.district, p.party].filter(Boolean).join(" · ")}
                  </span>
                </div>
                <span className="shrink-0 text-xs text-slate-500">
                  {p.sponsored_count} bill{p.sponsored_count === 1 ? "" : "s"}
                </span>
              </li>
            ))}
          </ul>

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
