"use client";

import { useState } from "react";
import { diffWordsWithSpace } from "diff";

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
  const parts = expanded ? diffWordsWithSpace(baseText, amendedText) : [];

  return (
    <div className="mt-1">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="text-xs font-medium text-sunshine-600 underline hover:text-sunshine-500"
      >
        {expanded ? "Hide changes" : "View changes"}
      </button>
      {expanded && (
        <div className="mt-2 rounded-md border border-slate-200 bg-slate-50 p-3">
          <p className="mb-2 text-[11px] text-slate-400">
            Diffed against the bill&apos;s current stored text, not necessarily the version
            immediately before this amendment — see caveat in source. Added text is highlighted,
            removed text is struck through.
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
