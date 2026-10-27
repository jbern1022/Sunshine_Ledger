"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { fetchSourceStatus } from "@/lib/api";
import { formatChecked, nightlySummary } from "@/lib/freshness";
import { t, tRich } from "@/lib/i18n";
import type { SourceStatus } from "@/lib/types";

/** One line under the bill list header: how fresh the bill data is, with a
 *  link to the full source list. If the status can't be fetched it says so
 *  rather than vanishing -- silence would read as "up to date". */
export default function DataFreshness() {
  const [statuses, setStatuses] = useState<SourceStatus[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetchSourceStatus()
      .then(setStatuses)
      .catch(() => setFailed(true));
  }, []);

  const link = (
    <Link href="/methodology#data-sources" className="text-sunshine-700 underline hover:text-sunshine-800">
      {t("freshness.link")}
    </Link>
  );

  if (failed) {
    return (
      <p className="mt-1 text-xs text-amber-800" role="status">
        {tRich("freshness.failed", { link })}
      </p>
    );
  }
  if (!statuses) return null; // still loading
  const { lastChecked, stale } = nightlySummary(statuses);

  if (stale.length > 0) {
    return (
      <p className="mt-1 text-xs text-amber-800" role="status">
        {tRich("freshness.stale", { sources: stale.map((s) => s.label).join(", "), link })}
      </p>
    );
  }
  if (lastChecked === null) {
    return (
      <p className="mt-1 text-xs text-amber-800" role="status">
        {tRich("freshness.neverChecked", { link })}
      </p>
    );
  }
  return (
    <p className="mt-1 text-xs text-slate-500">
      {tRich("freshness.ok", { date: formatChecked(lastChecked), link })}
    </p>
  );
}
