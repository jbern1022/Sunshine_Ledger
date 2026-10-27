"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { fetchSourceStatus } from "@/lib/api";
import { formatChecked, nightlySummary } from "@/lib/freshness";
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
      About our data
    </Link>
  );

  if (failed) {
    return (
      <p className="mt-1 text-xs text-amber-800" role="status">
        We couldn&apos;t check how recently the data was updated, so these bills may be out of date · {link}
      </p>
    );
  }
  if (!statuses) return null; // still loading
  const { lastChecked, stale } = nightlySummary(statuses);

  if (stale.length > 0) {
    return (
      <p className="mt-1 text-xs text-amber-800" role="status">
        Not updated on schedule: {stale.map((s) => s.label).join(", ")}. Some bills may be out of date · {link}
      </p>
    );
  }
  if (lastChecked === null) {
    return (
      <p className="mt-1 text-xs text-amber-800" role="status">
        At least one source has no recorded update yet, so some bills may be missing or out of date · {link}
      </p>
    );
  }
  return (
    <p className="mt-1 text-xs text-slate-500">
      State and local bills are checked nightly · last checked {formatChecked(lastChecked)} · {link}
    </p>
  );
}
