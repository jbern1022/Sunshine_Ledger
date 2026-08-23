"use client";

import { useEffect, useState } from "react";
import { fetchElections } from "@/lib/api";
import type { ElectionCalendar } from "@/lib/types";

/** Election calendar strip (BRD 5.8).
 *
 *  BRD 5.8 allows surfacing the calendar "without scoring or predictive
 *  claims at MVP", so this shows published dates and says outright that the
 *  site doesn't connect bills to candidates or races. Stating the non-claim
 *  matters as much as the dates: putting an election date next to a list of
 *  bills invites readers to infer a link this project isn't making, and the
 *  Roadmap gates electioneering-adjacent work behind a legal review that
 *  hasn't happened.
 *
 *  Renders nothing on error. A civic calendar is useful context, never a
 *  reason to break the page it sits above.
 */
export default function ElectionContext() {
  const [calendar, setCalendar] = useState<ElectionCalendar | null>(null);

  useEffect(() => {
    fetchElections()
      .then(setCalendar)
      .catch(() => setCalendar(null));
  }, []);

  if (!calendar) return null;

  const next = calendar.next_event;
  const electionDay = calendar.events.find((e) => e.kind === "election" && !e.is_past);

  return (
    <div className="mb-6 rounded-md border border-slate-200 bg-white px-4 py-3 text-xs">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="font-semibold text-ledger-900">
          {calendar.state} {calendar.year} election calendar
        </span>
        {next ? (
          <span className="text-slate-600">
            Next: <span className="font-medium">{next.label}</span> —{" "}
            {new Date(next.date + "T00:00:00").toLocaleDateString(undefined, {
              month: "long",
              day: "numeric",
              year: "numeric",
            })}{" "}
            <span className="text-slate-400">
              ({next.days_away === 0 ? "today" : `in ${next.days_away} days`})
            </span>
          </span>
        ) : (
          <span className="text-slate-500">No further dates on the {calendar.year} calendar.</span>
        )}
        {electionDay && next && electionDay.label !== next.label && (
          <span className="text-slate-400">
            · {electionDay.label}{" "}
            {new Date(electionDay.date + "T00:00:00").toLocaleDateString(undefined, {
              month: "short",
              day: "numeric",
            })}
          </span>
        )}
      </div>
      <p className="mt-1.5 text-[11px] leading-relaxed text-slate-400">
        Dates published by the{" "}
        <a
          href={calendar.source.url}
          target="_blank"
          rel="noreferrer"
          className="underline hover:text-slate-600"
        >
          {calendar.source.name}
        </a>
        . Shown as civic context only — Sunshine Ledger does not link bills to candidates, parties,
        or races, and makes no claim about how any bill bears on an election.
      </p>
    </div>
  );
}
