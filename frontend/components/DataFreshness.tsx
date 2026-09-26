"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { fetchSourceStatus } from "@/lib/api";
import { formatChecked, nightlySummary } from "@/lib/freshness";
import type { SourceStatus } from "@/lib/types";

/** One line under the bill list header: how fresh the bill data is, with a
 *  link to the full source list. Renders nothing if the status can't be
 *  fetched -- a missing note beats a wrong one. */
export default function DataFreshness() {
  const [statuses, setStatuses] = useState<SourceStatus[] | null>(null);

  useEffect(() => {
    fetchSourceStatus()
      .then(setStatuses)
      .catch(() => setStatuses(null));
  }, []);

  if (!statuses) return null;
  const { lastChecked, stale } = nightlySummary(statuses);
  const link = (
    <Link href="/methodology#data-sources" className="text-sunshine-700 underline hover:text-sunshine-800">
      About our data
    </Link>
  );

  if (stale.length > 0) {
    return (
      <p className="mt-1 text-xs text-amber-800" role="status">
        Not updated on schedule: {stale.map((s) => s.label).join(", ")}. Some bills may be out of date · {link}
      </p>
    );
  }
  return (
    <p className="mt-1 text-xs text-slate-500">
      State and local bills are checked nightly · last checked {formatChecked(lastChecked)} · {link}
    </p>
  );
}
