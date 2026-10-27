"use client";

import { useEffect, useState } from "react";

import { fetchSourceStatus } from "@/lib/api";
import { t } from "@/lib/i18n";

/** The methodology page's coverage limit, counted from GET /sources/status so
 *  it stays true as cities and counties are onboarded. Until the status loads,
 *  or if it can't, the wording makes no numeric claim. */
export default function CoverageSummary() {
  const [localCount, setLocalCount] = useState<number | null>(null);

  useEffect(() => {
    fetchSourceStatus()
      .then((statuses) =>
        // Local governments: a bill source tied to a place other than the state,
        // with records. A registered place with no rows yet isn't coverage.
        setLocalCount(statuses.filter((s) => s.jurisdiction && s.jurisdiction !== "FL" && (s.bill_count ?? 0) > 0).length),
      )
      .catch(() => setLocalCount(null));
  }, []);

  const local = localCount === null ? t("coverage.localUnknown") : t("coverage.local", { count: localCount });

  return (
    <>
      <span className="font-medium">{t("coverage.partial")}</span> {t("coverage.rest", { local })}
    </>
  );
}
