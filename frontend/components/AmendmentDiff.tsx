"use client";

import { useState } from "react";
import { diffWordsWithSpace } from "diff";
import { t } from "@/lib/i18n";
import { lawAsAmended } from "@/lib/changeMarkers";

/** Word-level diff between the bill's stored full text and one amendment's
 *  document text -- added text highlighted, removed text struck through.
 *
 *  CAVEAT: `baseText` is the bill's *current* stored full_text, not a
 *  snapshot of the bill as it stood immediately before this specific
 *  amendment. LegiScan doesn't expose per-amendment "before" text, and
 *  building true version history would mean storing a full_text snapshot
 *  per ingestion run. For a bill amended once this is exactly right; for
 *  one amended multiple times, only the most recent amendment's diff
 *  against current text is meaningful -- earlier amendments will show as
 *  diffing against text that has since moved on. Good enough for the
 *  headline case this exists for (a "gutting amendment" that replaces a
 *  bill's substance wholesale), not a full version history.
 */
export default function AmendmentDiff({ baseText, amendedText }: { baseText: string; amendedText: string }) {
  const [expanded, setExpanded] = useState(false);
  // Both texts can carry the bill's own inline `[deleted: …]`/`[added: …]`
  // markers. Diff the law as each version would read it, so the markers'
  // brackets and struck wording don't show up as spurious changes.
  const parts = expanded ? diffWordsWithSpace(lawAsAmended(baseText), lawAsAmended(amendedText)) : [];

  return (
    <div className="mt-1">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="text-xs font-medium text-sunshine-700 underline hover:text-sunshine-800"
      >
        {expanded ? t("diff.hide") : t("diff.view")}
      </button>
      {expanded && (
        <div className="mt-2 rounded-md border border-slate-200 bg-slate-50 p-3">
          <p className="mb-2 text-[11px] text-slate-500">
            {t("diff.caveat")}
          </p>
          <p className="whitespace-pre-wrap font-mono text-xs leading-relaxed">
            {parts.map((part, i) => (
              <span
                key={i}
                className={
                  part.added
                    ? "bg-emerald-100 text-emerald-900"
                    : part.removed
                      ? "text-red-700 line-through decoration-red-400"
                      : "text-slate-700"
                }
              >
                {part.value}
              </span>
            ))}
          </p>
        </div>
      )}
    </div>
  );
}
