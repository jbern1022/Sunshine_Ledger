"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { fetchPerson } from "@/lib/api";
import type { PersonDetail } from "@/lib/types";

/** One sponsor and the bills they're attached to.
 *
 *  May be a person, a committee, or an office -- city records use all
 *  three, so the copy avoids calling every entry a legislator.
 *
 *  Strictly a record of sponsorship drawn from bill data. No voting record,
 *  no consistency score, no characterisation of the person — those are
 *  Phase 2/3 on the Roadmap and sit behind a legal review that hasn't
 *  happened.
 */
export default function PersonPage() {
  const params = useParams<{ id: string }>();
  const [person, setPerson] = useState<PersonDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!params?.id) return;
    fetchPerson(params.id)
      .then(setPerson)
      .catch(() => setError("This sponsor could not be found."));
  }, [params?.id]);

  if (error) {
    return (
      <div>
        <p className="text-sm text-slate-500">{error}</p>
        <Link href="/people" className="mt-3 inline-block text-sm text-sunshine-600 underline">
          ← All sponsors
        </Link>
      </div>
    );
  }

  if (!person) return <p className="text-sm text-slate-400">Loading…</p>;

  return (
    <div>
      <Link href="/people" className="text-xs text-sunshine-600 underline">
        ← All sponsors
      </Link>

      <h1 className="mt-3 text-2xl font-bold text-ledger-900">{person.name}</h1>
      <p className="mt-1 text-sm text-slate-500">
        {[person.role, person.district, person.party, person.jurisdiction_name]
          .filter(Boolean)
          .join(" · ")}
      </p>

      <p className="mt-4 text-sm text-slate-600">
        Attached to <span className="font-medium">{person.sponsored_count}</span> tracked bill
        {person.sponsored_count === 1 ? "" : "s"}. This is a record of sponsorship only — it is not a
        voting record, and nothing here rates or characterises this sponsor.
      </p>

      {person.bills.length === 0 ? (
        <p className="mt-4 text-sm text-slate-400">No tracked bills for this sponsor.</p>
      ) : (
        <ul className="mt-4 space-y-3">
          {person.bills.map((b) => (
            <li key={`${b.entity_id}-${b.relationship_type}`} className="rounded-lg border border-slate-200 bg-white p-4">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <Link href={`/bills/${b.entity_id}`} className="text-sm font-semibold text-sunshine-600 underline">
                  {b.bill_number}
                </Link>
                <span className="text-xs text-slate-400">
                  {b.relationship_type === "co_sponsor" ? "co-sponsor" : "sponsor"}
                  {b.last_action_date && ` · last action ${b.last_action_date}`}
                </span>
              </div>
              {b.what_it_does ? (
                <p className="mt-1.5 text-sm leading-relaxed text-slate-700">{b.what_it_does}</p>
              ) : (
                <p className="mt-1.5 text-sm italic text-slate-400">No summary generated yet.</p>
              )}
              <p className="mt-1 text-xs text-slate-400">{b.status}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
