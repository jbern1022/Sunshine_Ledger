"use client";

import { useState } from "react";
import Link from "next/link";

import { hasTopic } from "@/lib/votingRecord";
import type { PersonBillItem } from "@/lib/types";

const FIRST = 10;

/** The bills a sponsor is attached to, filtered by the page's topic slicer:
 *  the first ten, then all of them on request (some legislators have 100+). */
export default function SponsoredBills({
  bills,
  topic,
  topicLabel,
}: {
  bills: PersonBillItem[];
  topic: string;
  topicLabel?: string;
}) {
  const [all, setAll] = useState(false);
  const matching = bills.filter((b) => hasTopic(b, topic));
  const visible = all ? matching : matching.slice(0, FIRST);

  if (bills.length === 0) {
    return <p className="mt-4 text-sm text-slate-500">No tracked bills for this sponsor.</p>;
  }

  return (
    <section className="mt-6" aria-labelledby="sponsored-bills-heading">
      <h2 id="sponsored-bills-heading" className="text-sm font-semibold text-ledger-900">
        {topicLabel ? `Sponsored and co-sponsored bills tagged ${topicLabel}` : "Sponsored and co-sponsored bills"}
        <span className="font-normal text-slate-500"> ({matching.length})</span>
      </h2>
      {matching.length === 0 ? (
        <p className="mt-2 text-sm text-slate-500">None of this sponsor&apos;s bills are tagged {topicLabel}.</p>
      ) : (
        <ul className="mt-2 space-y-3">
          {visible.map((b) => (
            <li
              key={`${b.entity_id}-${b.relationship_type}`}
              className="rounded-lg border border-slate-200 bg-white p-4"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <Link href={`/bills/${b.entity_id}`} className="text-sm font-semibold text-sunshine-700 underline">
                  {b.bill_number}
                </Link>
                <span className="text-xs text-slate-500">
                  {b.relationship_type === "co_sponsor" ? "co-sponsor" : "sponsor"}
                  {b.last_action_date && ` · last action ${b.last_action_date}`}
                </span>
              </div>
              {b.what_it_does ? (
                <p className="mt-1.5 text-sm leading-relaxed text-slate-700">{b.what_it_does}</p>
              ) : (
                <p className="mt-1.5 text-sm italic text-slate-500">No summary generated yet.</p>
              )}
              <p className="mt-1 text-xs text-slate-500">{b.status}</p>
            </li>
          ))}
        </ul>
      )}
      {matching.length > FIRST && (
        <button
          type="button"
          onClick={() => setAll(!all)}
          className="mt-2 text-xs font-medium text-sunshine-700 underline hover:text-sunshine-800"
        >
          {all ? `Show the first ${FIRST}` : `Show all ${matching.length}`}
        </button>
      )}
    </section>
  );
}
