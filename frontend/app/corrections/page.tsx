import type { Metadata } from "next";
import Link from "next/link";

import { t } from "@/lib/i18n";
import { getCorrections } from "@/lib/server-api";
import { CHANGE_TYPE_NAMES, changeLabel } from "@/lib/accountability";
import type { ChangeType } from "@/lib/types";

export const metadata: Metadata = {
  title: t("corrections.metaTitle"),
  description: t("corrections.metaDescription"),
  alternates: { types: { "application/rss+xml": [{ url: "/corrections/feed.xml", title: t("corrections.feedTitle") }] } },
};

const CHANGE_TYPES = Object.keys(CHANGE_TYPE_NAMES) as ChangeType[];
const SEVERITIES = { material: "corrections.sev.material", critical: "corrections.sev.critical" } as const;

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
      <h1 className="text-2xl font-bold text-ledger-900">{t("corrections.title")}</h1>
      <p className="mt-1 text-sm text-slate-600">
        {t("corrections.intro")}{" "}
        <Link href="/methodology#corrections" className="text-sunshine-700 underline">{t("corrections.how")}</Link>
        {" · "}
        <a href="/corrections/feed.xml" className="text-sunshine-700 underline">{t("corrections.rss")}</a>
      </p>

      <nav aria-label={t("corrections.filterAria")} className="mt-4 space-y-2 text-xs">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-slate-500">{t("corrections.kind")}</span>
          <FilterLink href={filterHref(undefined, severity)} active={!type}>{t("corrections.all")}</FilterLink>
          {CHANGE_TYPES.map((ct) => (
            <FilterLink key={ct} href={filterHref(ct, severity)} active={type === ct}>
              {CHANGE_TYPE_NAMES[ct]}
            </FilterLink>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-slate-500">{t("corrections.severity")}</span>
          {(Object.keys(SEVERITIES) as (keyof typeof SEVERITIES)[]).map((s) => (
            <FilterLink key={s} href={filterHref(type, s)} active={severity === s}>
              {t(SEVERITIES[s])}
            </FilterLink>
          ))}
        </div>
      </nav>

      {entries === null ? (
        <p className="mt-6 text-sm text-slate-600">{t("corrections.loadError")}</p>
      ) : entries.length === 0 ? (
        <p className="mt-6 text-sm text-slate-600">
          {type || severity === "critical"
            ? t("corrections.noMatch")
            : t("corrections.none")}
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
                  {c.bill_number ?? t("corrections.record")}
                  {c.bill_name ? ` — ${c.bill_name}` : ""}
                </Link>
              </p>
              <p className="mt-1 text-sm text-slate-700">{c.explanation}</p>
              {c.origin === "sunshine_ledger_ai" && (
                <p className="mt-0.5 text-[11px] text-slate-500">
                  {c.was_reviewed ? t("corrections.aiReviewed") : t("corrections.aiUnreviewed")}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
