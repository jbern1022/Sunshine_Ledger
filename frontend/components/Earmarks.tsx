import { t } from "@/lib/i18n";
import type { EarmarkList } from "@/lib/types";

const dollars = (n: number) => `$${n.toLocaleString("en-US")}`;

/** Community Project Funding the district's member asked for (or got). Every row says which stage it
 *  is at; a request is never presented as money awarded, and the section says what it leaves out. */
export default function Earmarks({ data, district }: { data: EarmarkList; district: string }) {
  if (data.total === 0) return null;
  return (
    <section className="mt-6" aria-labelledby="earmarks">
      <h2 id="earmarks" className="text-lg font-semibold text-ledger-900">{t("earmarks.title")}</h2>
      <p className="mt-1 text-xs text-slate-500">{data.note}</p>
      <ul className="mt-2 space-y-3">
        {data.items.map((e) => (
          <li key={e.id} className="rounded-md border border-slate-200 p-3 text-sm">
            <p>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700">{t(`earmarks.stage.${e.stage}`)}</span>{" "}
              <span className="font-medium text-slate-900">{e.recipient}</span>
              {e.amount !== null && <span className="text-slate-700"> · {dollars(e.amount)}</span>}
            </p>
            <p className="mt-1 text-slate-800">{e.description}</p>
            <p className="mt-1 text-xs text-slate-500">
              FY{e.fiscal_year} · {e.chamber === "senate" ? "Senate" : "House"} · {e.subcommittee} · {e.member}
              {e.party ? ` (${e.party})` : ""} · <a href={e.source_url} className="text-sunshine-700 underline" rel="noopener noreferrer">{t("earmarks.source")}</a>
            </p>
            <p className="mt-1 text-xs text-slate-500">{e.stage_label}</p>
          </li>
        ))}
      </ul>
      {data.total > data.items.length && (
        <p className="mt-2 text-xs text-slate-500">{t("earmarks.more", { shown: data.items.length, total: data.total, district })}</p>
      )}
    </section>
  );
}
