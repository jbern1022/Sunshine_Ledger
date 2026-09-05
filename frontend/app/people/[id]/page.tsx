import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getPerson } from "@/lib/server-api";

/** One sponsor and the bills they're attached to.
 *
 *  May be a person, a committee, or an office -- city records use all
 *  three, so the copy avoids calling every entry a legislator.
 *
 *  Server-rendered for the same reason as bill pages: "who sponsored this"
 *  is a question people put into a search engine, and a client-rendered
 *  page answers it with an empty shell.
 *
 *  Strictly a record of sponsorship drawn from bill data. No voting record,
 *  no consistency score, no characterisation of the sponsor -- those are
 *  Phase 2/3 on the Roadmap and sit behind a legal review that hasn't
 *  happened.
 */

type Props = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const person = await getPerson(id);
  if (!person) return { title: "Sponsor not found — Sunshine Ledger" };

  const qualifiers = [person.role, person.district].filter(Boolean).join(" ");
  const title = `${person.name}${qualifiers ? ` (${qualifiers})` : ""} | Sunshine Ledger`;
  const description =
    `Bills sponsored or co-sponsored by ${person.name}` +
    `${person.district ? `, ${person.district}` : ""} — ${person.sponsored_count} tracked. ` +
    "Sponsorship record only; no ratings or voting record.";

  return {
    title,
    description,
    openGraph: { title, description, type: "profile" },
    twitter: { card: "summary", title, description },
  };
}

export default async function PersonPage({ params }: Props) {
  const { id } = await params;
  const person = await getPerson(id);
  if (!person) notFound();

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

      {person.votes.length > 0 && (
        <section className="mt-4">
          <h2 className="text-sm font-semibold text-ledger-900">Voting record</h2>
          <p className="text-[11px] text-slate-400">
            Plain vote tallies from official roll calls — not a score, and not a claim about this
            sponsor.
          </p>
          <ul className="mt-1 space-y-1 text-sm">
            {person.votes.map((v, i) => (
              <li key={`${v.entity_id}-${i}`} className="flex flex-wrap items-baseline justify-between gap-2">
                <span>
                  <Link href={`/bills/${v.entity_id}`} className="text-sunshine-600 underline">
                    {v.bill_number}
                  </Link>
                  {v.roll_call_description && (
                    <span className="text-slate-400"> — {v.roll_call_description}</span>
                  )}
                </span>
                <span className="shrink-0 text-xs text-slate-500">
                  {v.vote}
                  {v.date && <span className="text-slate-400"> · {v.date}</span>}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {person.bills.length === 0 ? (
        <p className="mt-4 text-sm text-slate-400">No tracked bills for this sponsor.</p>
      ) : (
        <ul className="mt-4 space-y-3">
          {person.bills.map((b) => (
            <li
              key={`${b.entity_id}-${b.relationship_type}`}
              className="rounded-lg border border-slate-200 bg-white p-4"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <Link
                  href={`/bills/${b.entity_id}`}
                  className="text-sm font-semibold text-sunshine-600 underline"
                >
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
