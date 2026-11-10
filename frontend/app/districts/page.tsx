import type { Metadata } from "next";
import Link from "next/link";

import { getDistricts } from "@/lib/server-api";
import { t } from "@/lib/i18n";

export const metadata: Metadata = {
  title: "Districts — Sunshine Ledger",
  description: "Florida's House and Senate districts: who holds each seat, the bills filed from it, and Census estimates about its residents.",
};

export default async function DistrictsPage() {
  const data = await getDistricts();
  const groups = [
    { key: "house" as const, title: t("districts.house") },
    { key: "senate" as const, title: t("districts.senate") },
    { key: "us_house" as const, title: t("districts.congress") },
  ];
  return (
    <article>
      <h1 className="text-2xl font-bold text-ledger-900">{t("districts.title")}</h1>
      <p className="mt-1 text-sm text-slate-600">{t("districts.intro")}</p>
      {data === null && <p className="mt-6 text-sm text-slate-600">{t("districts.unavailable")}</p>}
      {[data?.map_plan, data?.congressional_map_plan].map(
        (plan) =>
          plan && (
            <p key={plan.key} className="mt-2 text-xs text-slate-500">
              {t("districts.plan", { name: plan.name, date: plan.effective_from })}
            </p>
          ),
      )}
      {data &&
        groups.map((g) => (
          <section key={g.key} className="mt-6" hidden={!data.items.some((d) => d.chamber === g.key)}>
            <h2 className="text-lg font-semibold text-ledger-900">{g.title}</h2>
            <ul className="mt-2 flex flex-wrap gap-1.5 text-xs">
              {data.items
                .filter((d) => d.chamber === g.key)
                .map((d) => (
                  <li key={d.code}>
                    <Link href={`/districts/${d.code}`} className="rounded-full border border-slate-300 px-2.5 py-0.5 text-slate-700 hover:border-slate-500">
                      {d.code}
                    </Link>
                  </li>
                ))}
            </ul>
          </section>
        ))}
    </article>
  );
}
