import type { Metadata } from "next";
import Link from "next/link";

import FlagPromise from "@/components/FlagPromise";
import { getPromises } from "@/lib/server-api";
import { t } from "@/lib/i18n";
import type { PromiseStatement } from "@/lib/types";

export const metadata: Metadata = {
  title: "Promises — Sunshine Ledger",
  description:
    "What 2026 Florida legislature winners said they would do, copied exactly from pages they published, with the source and the date we saved it.",
};

type Props = { searchParams: Promise<{ chamber?: string }> };

function groupByOfficial(items: PromiseStatement[]) {
  const groups = new Map<string, PromiseStatement[]>();
  for (const item of items) {
    const key = `${item.official.chamber}-${item.official.district}`;
    groups.set(key, [...(groups.get(key) ?? []), item]);
  }
  return [...groups.values()];
}

function labels(item: PromiseStatement): string | null {
  const l = item.automated_labels;
  if (item.review_state === "approved" && l.overridden_by_reviewer) return null;
  const parts = [l.commitment_type?.replace("_", " "), ...(l.topics ?? []).map((x) => x.replace(/_/g, " "))].filter(Boolean);
  return parts.length ? parts.join(", ") : null;
}

/** Public list of collected promise statements. Verbatim text only; never a
 *  paraphrase, a score or a verdict on whether anything was kept. */
export default async function PromisesPage({ searchParams }: Props) {
  const params = await searchParams;
  const chamber = params.chamber === "house" || params.chamber === "senate" ? params.chamber : undefined;
  const data = await getPromises({ chamber });

  return (
    <article>
      <h1 className="text-2xl font-bold text-ledger-900">{t("promises.title")}</h1>
      <p className="mt-1 text-sm text-slate-600">{t("promises.intro")}</p>
      {data && <p className="mt-2 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">{data.disclosure}</p>}

      <nav aria-label="Filter by chamber" className="mt-4 flex gap-1.5 text-xs">
        {[undefined, "house", "senate"].map((c) => (
          <Link
            key={c ?? "all"}
            href={c ? `/promises?chamber=${c}` : "/promises"}
            aria-current={chamber === c ? "page" : undefined}
            className={`rounded-full border px-2.5 py-0.5 ${
              chamber === c ? "border-ledger-900 bg-ledger-900 text-white" : "border-slate-300 text-slate-700 hover:border-slate-500"
            }`}
          >
            {c === "house" ? t("promises.chamber.house") : c === "senate" ? t("promises.chamber.senate") : "All"}
          </Link>
        ))}
      </nav>

      {data === null && <p className="mt-6 text-sm text-slate-600">{t("promises.unavailable")}</p>}
      {data && data.items.length === 0 && <p className="mt-6 text-sm text-slate-600">{t("promises.none")}</p>}

      {data &&
        groupByOfficial(data.items).map((group) => {
          const o = group[0].official;
          return (
            <section key={`${o.chamber}-${o.district}`} className="mt-8">
              <h2 className="text-lg font-semibold text-ledger-900">
                {t("promises.official", { name: o.name, chamber: o.chamber === "house" ? t("promises.chamber.house") : t("promises.chamber.senate"), district: o.district })}
                {o.party ? <span className="ml-2 text-sm font-normal text-slate-500">({o.party})</span> : null}
              </h2>
              {o.result_status !== "certified" && <p className="text-xs text-slate-500">{t("promises.certifiedNo")}</p>}
              {o.office_status && <p className="mt-1 text-xs font-medium text-slate-700">{o.office_status}</p>}
              <ul className="mt-3 space-y-4">
                {group.map((item) => (
                  <li key={item.id} className="rounded-md border border-slate-200 p-3">
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700">{item.review_label}</span>
                    <blockquote className="mt-2 border-l-4 border-sunshine-400 pl-3 text-sm text-slate-900">{item.quote}</blockquote>
                    <p className="mt-2 text-xs text-slate-600">
                      <a href={item.source_url} className="text-sunshine-700 underline" rel="noopener noreferrer">
                        {t("promises.source")}
                      </a>
                      {" · "}
                      {t("promises.saved", { date: new Date(item.snapshot.fetched_at).toLocaleDateString("en-US") })}
                      {item.snapshot.internet_archive_capture && (
                        <> {" · "}{t("promises.archive", { stamp: item.snapshot.internet_archive_capture })}</>
                      )}
                    </p>
                    {labels(item) && (
                      <p className="mt-1 text-xs text-slate-500">{t("promises.automatedLabels", { labels: labels(item)! })}</p>
                    )}
                    <FlagPromise id={item.id} />
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
    </article>
  );
}
