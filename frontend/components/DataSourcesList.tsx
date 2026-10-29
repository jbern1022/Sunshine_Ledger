"use client";

import { useEffect, useState } from "react";

import { fetchSourceStatus } from "@/lib/api";
import { formatChecked } from "@/lib/freshness";
import { t } from "@/lib/i18n";
import type { SourceStatus } from "@/lib/types";

/** Every data source with its schedule, last check, coverage and known
 *  gaps, for the methodology page (from GET /sources/status). */
export default function DataSourcesList() {
  const [statuses, setStatuses] = useState<SourceStatus[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetchSourceStatus()
      .then(setStatuses)
      .catch(() => setFailed(true));
  }, []);

  if (failed) {
    return <p className="mt-2 text-sm text-slate-600">{t("sources.unavailable")}</p>;
  }
  if (!statuses) {
    return <p className="mt-2 text-sm text-slate-500">{t("sources.loading")}</p>;
  }

  return (
    <ul className="mt-2 space-y-3 text-sm text-slate-700">
      {statuses.map((s) => (
        <li key={s.key}>
          <span className="font-medium text-ledger-900">{s.label}</span>
          <span className="text-slate-500">
            {" "}
            {t("sources.schedule", { schedule: s.schedule, date: formatChecked(s.last_checked_at) })}
          </span>
          {s.stale && <span className="text-amber-800">{t("sources.notOnSchedule")}</span>}
          {s.bill_count !== null && (
            <span className="block text-xs text-slate-500">
              {t("sources.bills", { count: s.bill_count })}
              {s.bills_with_text !== null && t("sources.withText", { count: s.bills_with_text })}
            </span>
          )}
          <span className="block">{s.note}</span>
        </li>
      ))}
    </ul>
  );
}
