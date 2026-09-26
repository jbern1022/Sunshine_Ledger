"use client";

import { useState } from "react";

import { becameLaw, buildTimeline, formatStepDate } from "@/lib/timeline";
import type { ActionOut, AmendmentOut, RollCallOut } from "@/lib/types";

interface Props {
  actions: ActionOut[];
  votes: RollCallOut[];
  amendments: AmendmentOut[];
  officialUrl: string | null;
}

/** A state bill's path, oldest first: key steps by default (filing,
 *  recorded votes, adopted amendments, outcome), every official history
 *  step on request. Plain facts from the official record -- no reasons,
 *  no for/against framing. */
export default function LegislativeTimeline({ actions, votes, amendments, officialUrl }: Props) {
  const [showAll, setShowAll] = useState(false);
  const steps = buildTimeline(actions, votes, amendments);
  if (steps.length === 0) return null;

  const shown = showAll ? steps : steps.filter((s) => s.key);
  const years = new Set(steps.map((s) => s.date.slice(0, 4)));

  return (
    <section className="mt-4" aria-labelledby="timeline-heading">
      <h2 id="timeline-heading" className="text-sm font-semibold text-ledger-900">
        {becameLaw(actions) ? "How it became law" : "Legislative history"}
      </h2>
      <p className="text-[11px] text-slate-500">
        From the official record.{" "}
        {showAll ? `All ${steps.length} steps.` : `Key steps: filing, recorded votes, adopted amendments and the outcome.`}
      </p>
      <ol className="mt-2 space-y-1.5 border-l border-slate-200 pl-3 text-sm">
        {shown.map((s, i) => (
          <li key={`${s.date}-${s.kind}-${i}`} className="grid grid-cols-[4.5rem_1fr] gap-2">
            <span className="text-xs tabular-nums text-slate-500">
              {formatStepDate(s.date)}
              {years.size > 1 && <span className="block">{s.date.slice(0, 4)}</span>}
            </span>
            <span className={s.key ? "text-slate-800" : "text-slate-600"}>
              {s.href ? (
                <a href={s.href} className="underline decoration-slate-300 hover:text-sunshine-800">
                  {s.text}
                </a>
              ) : (
                s.text
              )}
              {s.detail && <span className="font-medium"> · {s.detail}</span>}
              {s.chamber && <span className="text-xs text-slate-500"> · {s.chamber}</span>}
            </span>
          </li>
        ))}
      </ol>
      <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
        {steps.length > shown.length || showAll ? (
          <button
            type="button"
            onClick={() => setShowAll(!showAll)}
            aria-expanded={showAll}
            className="font-medium text-sunshine-700 underline hover:text-sunshine-800"
          >
            {showAll ? "Show key steps only" : `Show all ${steps.length} steps`}
          </button>
        ) : null}
        {officialUrl && (
          <a href={officialUrl} target="_blank" rel="noreferrer" className="text-sunshine-700 underline">
            Official bill history ↗
          </a>
        )}
      </div>
    </section>
  );
}
