import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getBill } from "@/lib/server-api";

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
  const bill = await getBill(id);
  if (!bill) notFound();

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
      <Link href="/" className="text-xs text-sunshine-600 underline">
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
      </header>

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

      {bill.sponsors.length > 0 && (
        <section className="mt-4">
          <h2 className="text-sm font-semibold text-ledger-900">Sponsors</h2>
          <ul className="mt-1 space-y-0.5 text-sm text-slate-700">
            {bill.sponsors.map((s) => (
              <li key={s.entity_id}>
                <Link href={`/people/${s.entity_id}`} className="text-sunshine-600 underline">
                  {s.name}
                </Link>
                {s.relationship_type === "co_sponsor" && (
                  <span className="text-slate-400"> (co-sponsor)</span>
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
          {bill.last_action_date && <span className="text-slate-400"> ({bill.last_action_date})</span>}
        </p>
      </section>

      {sources.length > 0 && (
        <section className="mt-4">
          <h2 className="text-sm font-semibold text-ledger-900">Sources</h2>
          <ul className="mt-1 space-y-1 text-sm">
            {sources.map((s) => (
              <li key={s.id}>
                <a href={s.url} target="_blank" rel="noreferrer" className="text-sunshine-600 underline">
                  {s.publisher ?? s.url}
                </a>
                <span className="text-slate-400">
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
          <p className="text-[11px] text-slate-400">
            Matched by keyword, unscored — their presence is not a claim about the bill.
          </p>
          <ul className="mt-1 space-y-1 text-sm">
            {bill.news.map((n) => (
              <li key={n.id}>
                <a href={n.url} target="_blank" rel="noreferrer" className="text-sunshine-600 underline">
                  {n.title}
                </a>
                <span className="text-slate-400"> — {n.publisher ?? "unknown outlet"}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {summaryModels.length > 0 && (
        <p className="mt-6 border-t border-slate-200 pt-3 text-[11px] leading-relaxed text-slate-400">
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

      {bill.full_text_url && (
        <p className="mt-3 text-sm">
          <a href={bill.full_text_url} target="_blank" rel="noreferrer" className="text-sunshine-600 underline">
            Read the original bill ↗
          </a>
        </p>
      )}
    </article>
  );
}
