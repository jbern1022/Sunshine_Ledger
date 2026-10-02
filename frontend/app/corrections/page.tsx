import type { Metadata } from "next";
import Link from "next/link";

import { getCorrections } from "@/lib/server-api";
import { CHANGE_TYPE_NAMES, changeLabel } from "@/lib/accountability";
import type { ChangeType } from "@/lib/types";

export const metadata: Metadata = {
  title: "Corrections — Sunshine Ledger",
  description:
    "Every material or critical correction, update, clarification and retraction Sunshine Ledger has made, newest first, with the earlier version and the reason.",
  alternates: { types: { "application/rss+xml": [{ url: "/corrections/feed.xml", title: "Sunshine Ledger — corrections" }] } },
};

const CHANGE_TYPES = Object.keys(CHANGE_TYPE_NAMES) as ChangeType[];
const SEVERITIES = { material: "Material and Critical", critical: "Critical only" } as const;

type Props = { searchParams: Promise<{ type?: string; severity?: string }> };

function filterHref(type: string | undefined, severity: string | undefined) {
  const qs = new URLSearchParams();
  if (type) qs.set("type", type);
  if (severity && severity !== "material") qs.set("severity", severity);
  const s = qs.toString();
  return s ? `/corrections?${s}` : "/corrections";
}

function FilterLink({ href, active, children }: { href: string; active: boolean; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={`rounded-full border px-2.5 py-0.5 ${
        active ? "border-ledger-900 bg-ledger-900 text-white" : "border-slate-300 text-slate-700 hover:border-slate-500"
      }`}
    >
      {children}
    </Link>
  );
}

/** Site-wide corrections log (correction-process spec, step 4). Material and
 *  Critical only; Minor fixes stay on each bill's own history. */
export default async function CorrectionsPage({ searchParams }: Props) {
  const params = await searchParams;
  const type = CHANGE_TYPES.includes(params.type as ChangeType) ? (params.type as ChangeType) : undefined;
  const severity = params.severity === "critical" ? "critical" : "material";
  const entries = await getCorrections({ change_type: type, severity });

  return (
    <article>
      <h1 className="text-2xl font-bold text-ledger-900">Corrections</h1>
      <p className="mt-1 text-sm text-slate-600">
        Every material or critical change Sunshine Ledger has made to something it published, newest first. Each
        entry keeps the earlier version and says why it changed. Corrections to AI-generated analysis are listed like
        any other. Minor fixes, such as typos and broken links, are listed only on the page they affect.{" "}
        <Link href="/methodology#corrections" className="text-sunshine-700 underline">How corrections work</Link>
        {" · "}
        <a href="/corrections/feed.xml" className="text-sunshine-700 underline">Follow by RSS</a>
      </p>

      <nav aria-label="Filter corrections" className="mt-4 space-y-2 text-xs">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-slate-500">Kind:</span>
          <FilterLink href={filterHref(undefined, severity)} active={!type}>All</FilterLink>
          {CHANGE_TYPES.map((t) => (
            <FilterLink key={t} href={filterHref(t, severity)} active={type === t}>
              {CHANGE_TYPE_NAMES[t]}
            </FilterLink>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-slate-500">Severity:</span>
          {(Object.keys(SEVERITIES) as (keyof typeof SEVERITIES)[]).map((s) => (
            <FilterLink key={s} href={filterHref(type, s)} active={severity === s}>
              {SEVERITIES[s]}
            </FilterLink>
          ))}
        </div>
      </nav>

      {entries === null ? (
        <p className="mt-6 text-sm text-slate-600">The corrections log couldn&apos;t be loaded just now. Try again shortly.</p>
      ) : entries.length === 0 ? (
        <p className="mt-6 text-sm text-slate-600">
          {type || severity === "critical"
            ? "No corrections match these filters."
            : "No material or critical corrections have been published yet."}
        </p>
      ) : (
        <ul className="mt-5 space-y-3">
          {entries.map((c) => (
            <li key={c.id} className="rounded-md border border-slate-200 p-3">
              <p className="text-sm">
                <span className="font-medium text-ledger-900">{changeLabel(c)}</span>
                <span className="text-slate-600">
                  {" "}
                  · {CHANGE_TYPE_NAMES[c.change_type]} ({c.severity})
                </span>
              </p>
              <p className="mt-0.5 text-sm">
                <Link href={`/bills/${c.bill_entity_id}#correction-${c.id}`} className="text-sunshine-700 underline">
                  {c.bill_number ?? "Record"}
                  {c.bill_name ? ` — ${c.bill_name}` : ""}
                </Link>
              </p>
              <p className="mt-1 text-sm text-slate-700">{c.explanation}</p>
              {c.origin === "sunshine_ledger_ai" && (
                <p className="mt-0.5 text-[11px] text-slate-500">
                  The changed text was AI-generated{c.was_reviewed ? " and had been reviewed by a person" : ", not reviewed by a person"}.
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
