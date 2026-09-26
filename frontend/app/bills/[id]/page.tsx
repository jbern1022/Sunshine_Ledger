import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getBill, getSourceStatus } from "@/lib/server-api";
import { formatChecked, sourceForBill } from "@/lib/freshness";
import TagBadges from "@/components/TagBadges";
import AmendmentDiff from "@/components/AmendmentDiff";
import MarkedText from "@/components/MarkedText";
import BillLayers from "@/components/BillLayers";
import LegislativeTimeline from "@/components/LegislativeTimeline";
import { hasAnyLayer } from "@/lib/layers";

/** Permalink for a single bill.
 *
 *  Rendered on the server rather than fetched in the browser. Bills only
 *  existed as expandable cards before this page, so there was no address to
 *  share -- and an address nobody can find is barely an improvement: the
 *  first client-rendered version returned an empty shell to crawlers, with
 *  "Sunshine Ledger" as the title for all 2,375 bills. People find
 *  legislation through search, so the content has to be in the HTML.
 *
 *  Pure display, no interactivity, so no client component is needed.
 */

type Props = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const bill = await getBill(id);
  if (!bill) return { title: "Bill not found — Sunshine Ledger" };

  // Prefer the plain-language summary for the description: it's written for
  // a general audience, which is exactly what a search result needs.
  const description = (bill.what_it_does ?? bill.name ?? "").slice(0, 300);
  const title = `${bill.bill_number} — ${bill.jurisdiction_name ?? "Florida"} | Sunshine Ledger`;

  return {
    title,
    description,
    openGraph: { title, description, type: "article" },
    twitter: { card: "summary", title, description },
  };
}

export default async function BillPage({ params }: Props) {
  const { id } = await params;
  const [bill, statuses] = await Promise.all([getBill(id), getSourceStatus()]);
  if (!bill) notFound();
  const dataSource = sourceForBill(statuses, bill.source_system);
  const legislatorSponsors = bill.sponsors.filter((s) => !s.is_committee);
  const committeeSponsors = bill.sponsors.filter((s) => s.is_committee);

  const summaryModels = Array.from(
    new Set(
      bill.claims
        .filter((c) => c.generated_by.startsWith("llm:"))
        .map((c) => c.generated_by.slice("llm:".length)),
    ),
  );
  const whoItAffects = bill.claims.find((c) => c.claim_type === "who_it_affects")?.claim_text;
  const sources = Array.from(
    new Map(bill.claims.flatMap((c) => c.sources).map((s) => [s.id, s])).values(),
  );

  return (
    <article>
      <Link href="/" className="text-xs text-sunshine-700 underline">
        ← All bills
      </Link>

      <header className="mt-3">
        <div className="flex flex-wrap items-center gap-2 text-xs font-medium text-slate-500">
          <span>{bill.jurisdiction_name ?? "Florida"}</span>
          {bill.chamber && (
            <>
              <span>·</span>
              <span>{bill.chamber}</span>
            </>
          )}
          {bill.session && (
            <>
              <span>·</span>
              <span>{bill.session}</span>
            </>
          )}
        </div>
        <h1 className="mt-1 text-2xl font-bold text-ledger-900">{bill.bill_number}</h1>
        <p className="mt-1 text-sm text-slate-600">{bill.name}</p>
        <TagBadges tags={bill.tags} />
      </header>

      {hasAnyLayer(bill.layers) ? (
        <BillLayers layers={bill.layers} hasStaffAnalysis={bill.has_staff_analysis} fallbackSummary={bill.what_it_does} />
      ) : (
        <>
          {bill.what_it_does && (
            <section className="mt-5">
              <h2 className="text-sm font-semibold text-ledger-900">What it does</h2>
              <p className="mt-1 text-sm leading-relaxed text-slate-700">{bill.what_it_does}</p>
            </section>
          )}

          {whoItAffects && (
            <section className="mt-4">
              <h2 className="text-sm font-semibold text-ledger-900">Who it affects</h2>
              <p className="mt-1 text-sm leading-relaxed text-slate-700">{whoItAffects}</p>
            </section>
          )}
        </>
      )}

      {bill.actions && bill.actions.length > 0 && (
        <LegislativeTimeline
          actions={bill.actions}
          votes={bill.votes}
          amendments={bill.amendments}
          officialUrl={bill.full_text_url}
        />
      )}

      {bill.sponsors.length > 0 && (
        <section className="mt-4">
          <h2 className="text-sm font-semibold text-ledger-900">Sponsors</h2>
          {legislatorSponsors.length > 0 && (
            <ul className="mt-1 space-y-0.5 text-sm text-slate-700">
              {legislatorSponsors.map((s) => (
                <li key={s.entity_id}>
                  <Link href={`/people/${s.entity_id}`} className="text-sunshine-700 underline">
                    {s.name}
                  </Link>
                  {s.relationship_type === "co_sponsor" && (
                    <span className="text-slate-500"> (co-sponsor)</span>
                  )}
                </li>
              ))}
            </ul>
          )}
          {committeeSponsors.length > 0 && (
            <p className="mt-2 text-sm text-slate-700">
              <span className="font-medium">Committee sponsors: </span>
              {committeeSponsors.map((s, i) => (
                <span key={s.entity_id}>
                  {i > 0 && "; "}
                  {s.name}
                </span>
              ))}
              <span className="block text-xs text-slate-500">
                The committees that produced this version of the bill (a committee substitute). A
                committee sponsoring a bill is not a legislator&apos;s endorsement.
              </span>
            </p>
          )}
        </section>
      )}

      {bill.votes.length > 0 && (
        <section className="mt-4">
          <h2 className="text-sm font-semibold text-ledger-900">Votes</h2>
          <p className="text-[11px] text-slate-500">
            Plain vote tallies from official roll calls — not a score, and not a claim about any
            legislator.
          </p>
          <ul className="mt-1 space-y-2 text-sm">
            {bill.votes.map((v) => (
              <li key={v.id} id={`roll-call-${v.roll_call_id}`} className="scroll-mt-4 rounded-md border border-slate-200 p-2">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="font-medium text-slate-700">{v.description}</span>
                  <span className="text-xs text-slate-500">{v.date}</span>
                </div>
                <p className="mt-0.5 text-xs text-slate-500">
                  {v.passed ? "Passed" : "Failed"} {v.yea}-{v.nay}
                  {v.nv ? `, ${v.nv} not voting` : ""}
                  {v.absent ? `, ${v.absent} absent` : ""}
                </p>
                {v.votes.length > 0 && (
                  <details className="mt-1">
                    <summary className="cursor-pointer text-xs text-sunshine-700 underline">
                      {v.votes.length} individual vote{v.votes.length === 1 ? "" : "s"}
                    </summary>
                    <ul className="mt-1 grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs text-slate-600 sm:grid-cols-3">
                      {v.votes.map((iv) => (
                        <li key={iv.person_entity_id}>
                          <Link
                            href={`/people/${iv.person_entity_id}`}
                            className="underline hover:text-slate-800"
                          >
                            {iv.person_name}
                          </Link>
                          : {iv.vote}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
                {v.source_url && (
                  <a
                    href={v.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-1 inline-block text-xs text-sunshine-700 underline"
                  >
                    View roll call ↗
                  </a>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {bill.amendments.length > 0 && (
        <section className="mt-4">
          <h2 className="text-sm font-semibold text-ledger-900">Amendment history</h2>
          <ul className="mt-1 space-y-1 text-sm text-slate-700">
            {bill.amendments.map((a) => (
              <li key={a.id} id={`amendment-${a.id}`} className="scroll-mt-4">
                Amendment filed {a.date}
                {a.chamber && <> in {a.chamber}</>}
                {a.adopted ? " — adopted" : " — not adopted"}
                {a.description && <span className="text-slate-500"> — {a.description}</span>}
                {a.amendment_text && bill.full_text && (
                  <AmendmentDiff baseText={bill.full_text} amendedText={a.amendment_text} />
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="mt-4 text-sm text-slate-600">
        <h2 className="text-sm font-semibold text-ledger-900">Status</h2>
        <p className="mt-1">
          {bill.status}
          {bill.last_action && <> — {bill.last_action}</>}
          {bill.last_action_date && <span className="text-slate-500"> ({bill.last_action_date})</span>}
        </p>
      </section>

      {sources.length > 0 && (
        <section className="mt-4">
          <h2 className="text-sm font-semibold text-ledger-900">Sources</h2>
          <ul className="mt-1 space-y-1 text-sm">
            {sources.map((s) => (
              <li key={s.id}>
                <a href={s.url} target="_blank" rel="noreferrer" className="text-sunshine-700 underline">
                  {s.publisher ?? s.url}
                </a>
                <span className="text-slate-500">
                  {" "}
                  — retrieved {new Date(s.retrieved_at).toLocaleDateString("en-US")}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {bill.news.length > 0 && (
        <section className="mt-4">
          <h2 className="text-sm font-semibold text-ledger-900">Recent news mentions</h2>
          <p className="text-[11px] text-slate-500">
            Matched by keyword, unscored — their presence is not a claim about the bill.
          </p>
          <ul className="mt-1 space-y-1 text-sm">
            {bill.news.map((n) => (
              <li key={n.id}>
                <a href={n.url} target="_blank" rel="noreferrer" className="text-sunshine-700 underline">
                  {n.title}
                </a>
                <span className="text-slate-500"> — {n.publisher ?? "unknown outlet"}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {summaryModels.length > 0 && (
        <p className="mt-6 border-t border-slate-200 pt-3 text-[11px] leading-relaxed text-slate-500">
          The plain-language summaries above were written by an AI model (
          {summaryModels.join(", ")}) from the sources listed here, and are published without a
          human reviewing each one. They can be wrong or incomplete — the linked source is the
          authority. See{" "}
          <Link href="/methodology" className="underline hover:text-slate-600">
            how this works
          </Link>
          .
        </p>
      )}

      {bill.full_text && (
        <section className="mt-4">
          <details>
            <summary className="cursor-pointer text-sm font-semibold text-ledger-900">
              Full bill text
            </summary>
            <p className="mt-1 whitespace-pre-line text-xs leading-relaxed text-slate-600">
              <MarkedText text={bill.full_text} />
            </p>
          </details>
        </section>
      )}

      {bill.full_text_url && (
        <p className="mt-3 text-sm">
          <a href={bill.full_text_url} target="_blank" rel="noreferrer" className="text-sunshine-700 underline">
            Read the original bill ↗
          </a>
        </p>
      )}

      {bill.source_system === "iqm2" && (
        <p className="mt-3 text-xs text-slate-500">
          Full text isn&apos;t available for Miami items: the city&apos;s portal doesn&apos;t publish it in a form
          we can collect.
        </p>
      )}

      {dataSource && (
        <p className="mt-3 text-xs text-slate-500">
          Source: {dataSource.label} · last checked {formatChecked(dataSource.last_checked_at)}
          {dataSource.stale && <span className="text-amber-800"> · may be out of date</span>} ·{" "}
          <Link href="/methodology#data-sources" className="text-sunshine-700 underline hover:text-sunshine-800">
            About our data
          </Link>
        </p>
      )}
    </article>
  );
}
