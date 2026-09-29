import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getPerson } from "@/lib/server-api";
import PersonRecord from "@/components/PersonRecord";
import { ALL_TOPICS, sponsorshipCounts } from "@/lib/votingRecord";

/** One sponsor and the bills they're attached to.
 *
 *  May be a person, a committee, or an office -- city records use all
 *  three, so the copy avoids calling every entry a legislator.
 *
 *  Server-rendered for the same reason as bill pages: "who sponsored this"
 *  is a question people put into a search engine, and a client-rendered
 *  page answers it with an empty shell.
 *
 *  Sponsorship and recorded roll-call votes drawn from official records,
 *  filterable by bill topic. No consistency score, no characterisation of
 *  the sponsor, no reasons for votes -- those are Phase 2/3 on the Roadmap
 *  and sit behind a legal review that hasn't happened.
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
    "Sponsorships and recorded votes; no ratings or scores.";

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
  const isStateLegislator = person.jurisdiction_name === "FL" && !person.is_committee;
  const sponsorship = sponsorshipCounts(person.bills, ALL_TOPICS);

  return (
    <div>
      <Link href="/people" className="text-xs text-sunshine-700 underline">
        ← All sponsors
      </Link>

      <h1 className="mt-3 text-2xl font-bold text-ledger-900">{person.name}</h1>
      <p className="mt-1 text-sm text-slate-500">
        {[person.role, person.district, person.party, person.jurisdiction_name]
          .filter(Boolean)
          .join(" · ")}
      </p>

      {person.is_committee ? (
        <p className="mt-4 text-sm text-slate-600">
          A committee, listed as a sponsor on the {person.sponsored_count} committee substitute
          {person.sponsored_count === 1 ? "" : "s"} it produced. Committees don&apos;t cast recorded votes.
        </p>
      ) : (
        <>
          <p className="mt-4 text-sm font-medium text-ledger-900">
            {[
              `Sponsored ${sponsorship.sponsored}`,
              `Co-sponsored ${sponsorship.cosponsored}`,
              ...(isStateLegislator
                ? [`${person.votes.length} recorded vote${person.votes.length === 1 ? "" : "s"}`]
                : []),
            ].join(" · ")}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Tracked bills and roll calls only. Nothing here rates or characterises this{" "}
            {isStateLegislator ? "legislator" : "sponsor"}.
          </p>
        </>
      )}

      <PersonRecord votes={person.votes} bills={person.bills}>
        {person.votes.length === 0 && isStateLegislator && (
          <p className="mt-4 text-sm text-slate-500">No recorded votes in the covered roll calls.</p>
        )}
        {!isStateLegislator && !person.is_committee && (
          <p className="mt-4 text-xs text-slate-500">Vote records aren&apos;t collected for local officials.</p>
        )}
      </PersonRecord>
    </div>
  );
}
