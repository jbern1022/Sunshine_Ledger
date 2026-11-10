import { t } from "@/lib/i18n";
import type { FloridaPlaces as FloridaPlacesData } from "@/lib/types";

/** Florida places a federal bill's text names, each with the sentence it is in
 *  (copied exactly). Found by rule, labelled automatic and unreviewed, and it
 *  says what it does not cover so an empty list is not read as "no effect". */
export default function FloridaPlaces({ data }: { data: FloridaPlacesData }) {
  const v = data.text_version;
  return (
    <section className="mt-5" aria-labelledby="fl-places">
      <h2 id="fl-places" className="text-sm font-semibold text-ledger-900">{t("federal.places.title")}</h2>
      <p className="text-xs text-slate-500">{data.label}</p>
      {v ? (
        <p className="mt-1 text-xs text-slate-500">
          {t("federal.places.version", { type: v.type ?? "printed", date: v.date ? ` (${v.date})` : "" })}{" "}
          <a href={v.source_url} className="text-sunshine-700 underline" rel="noopener noreferrer">{t("federal.places.source")}</a>
        </p>
      ) : (
        <p className="mt-2 text-sm text-slate-600">{t("federal.places.noText")}</p>
      )}
      {v && data.findings.length === 0 && <p className="mt-2 text-sm text-slate-600">{t("federal.places.none")}</p>}
      <ul className="mt-2 space-y-3">
        {data.findings.map((f, i) => (
          <li key={`${f.name}-${i}`} className="rounded-md border border-slate-200 p-3 text-sm">
            <p>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700">{t(`federal.places.kind.${f.kind}`)}</span>{" "}
              <span className="font-medium text-slate-900">{f.name}</span>
              {f.counties.length > 0 && <span className="text-xs text-slate-500"> · {t("federal.places.counties", { counties: f.counties.join(", ") })}</span>}
            </p>
            {f.section && <p className="mt-1 text-xs text-slate-500">{f.section}</p>}
            <blockquote className="mt-1 border-l-4 border-sunshine-400 pl-3 text-slate-800">{f.quote}</blockquote>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-slate-500">{data.not_covered}</p>
    </section>
  );
}
