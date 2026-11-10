import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { getDistrict } from "@/lib/server-api";
import { t } from "@/lib/i18n";
import type { DistrictMetric } from "@/lib/types";

type Props = { params: Promise<{ code: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { code } = await params;
  return { title: `${code} — Sunshine Ledger` };
}

function Value({ m }: { m: DistrictMetric }) {
  if (m.suppressed) return <span className="text-slate-500">{t("districts.suppressed")}</span>;
  const fmt = (n: number) => n.toLocaleString("en-US", { maximumFractionDigits: 1 });
  return (
    <span>
      <span className="font-medium text-slate-900">{m.estimate === null ? "—" : fmt(m.estimate)}</span>
      {m.unit ? <span className="text-slate-500"> {m.unit}</span> : null}
      {m.margin_of_error !== null && <span className="ml-2 text-slate-500">{t("districts.moe", { moe: fmt(m.margin_of_error) })}</span>}
      {m.reliability === "high_moe" && <span className="ml-2 text-amber-800">{t("districts.highMoe")}</span>}
    </span>
  );
}

export default async function DistrictPage({ params }: Props) {
  const { code } = await params;
  const d = await getDistrict(code);
  if (d === undefined) notFound();
  if (d === null) return <p className="text-sm text-slate-600">{t("districts.unavailable")}</p>;

  return (
    <article>
      <h1 className="text-2xl font-bold text-ledger-900">{d.code}</h1>
      <p className="mt-1 text-xs text-slate-500">{t("districts.plan", { name: d.map_plan.name, date: d.map_plan.effective_from })}</p>

      <section className="mt-6">
        <h2 className="text-lg font-semibold text-ledger-900">{t("districts.members")}</h2>
        {d.members.length === 0 ? (
          <p className="mt-2 text-sm text-slate-600">{t("districts.noMembers")}</p>
        ) : (
          <ul className="mt-2 space-y-1 text-sm">
            {d.members.map((m) => (
              <li key={`${m.person_entity_id}-${m.start_date ?? "roster"}`}>
                <Link href={`/people/${m.person_entity_id}`} className="text-sunshine-700 underline">{m.name}</Link>
                {m.party ? <span className="text-slate-500"> ({m.party})</span> : null}
                <span className="ml-2 text-xs text-slate-500">
                  {m.current ? t("districts.current") : t("districts.former")}
                  {m.start_date ? ` · ${m.start_date.slice(0, 4)}–${m.end_date ? m.end_date.slice(0, 4) : ""}` : ""}
                  {m.basis === "current_roster" ? ` · ${t("districts.basisRoster")}` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-6">
        <h2 className="text-lg font-semibold text-ledger-900">{t("districts.bills")}</h2>
        <p className="text-xs text-slate-500">{d.sponsored_bills.note}</p>
        {d.sponsored_bills.items.length === 0 ? (
          <p className="mt-2 text-sm text-slate-600">{t("districts.billsNone")}</p>
        ) : (
          <ul className="mt-2 space-y-1 text-sm">
            {d.sponsored_bills.items.map((b) => (
              <li key={b.entity_id}>
                <Link href={`/bills/${b.entity_id}`} className="text-sunshine-700 underline">{b.bill_number}</Link>{" "}
                <span className="text-slate-700">{b.name}</span> <span className="text-xs text-slate-500">· {b.status}</span>
              </li>
            ))}
          </ul>
        )}
        {d.sponsored_bills.total > d.sponsored_bills.items.length && (
          <p className="mt-2 text-xs">
            <Link href={`/?district=${d.code}`} className="text-sunshine-700 underline">
              {t("districts.billsAll", { count: d.sponsored_bills.total })}
            </Link>
          </p>
        )}
      </section>

      <section className="mt-6">
        <h2 className="text-lg font-semibold text-ledger-900">{t("districts.profile")}</h2>
        <p className="mt-1 rounded-md border border-slate-200 bg-slate-50 p-2 text-xs text-slate-700">{d.census_profile.label}</p>
        {d.census_profile.profile.length === 0 && <p className="mt-2 text-sm text-slate-600">{t("districts.profileNone")}</p>}
        {d.census_profile.profile.map((g) => (
          <div key={g.badge_slug} className="mt-4">
            <h3 className="text-sm font-semibold text-slate-800">{g.badge_label}</h3>
            <p className="text-xs text-slate-500">{t("districts.vintage", { vintage: g.vintage })}</p>
            <ul className="mt-1 space-y-1 text-sm">
              {g.metrics.map((m) => (
                <li key={m.label}>
                  <span className="text-slate-700">{m.label}: </span>
                  <Value m={m} />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>
    </article>
  );
}
