import { t } from "@/lib/i18n";
import { formatDate } from "@/lib/layers";
import type { StaffAnalysisExcerpt } from "@/lib/types";

// 'What legislative staff say this does' (Todoist 6j5J3C8qGR8XwgGG): the
// latest staff analysis's own Effect and Fiscal Impact sections, quoted, never
// paraphrased. The API joins PDF line wraps and moves footnotes to a Notes
// list; the words are the staff's.
const FIRST_PARAGRAPHS = 4;

function Paragraphs({ text }: { text: string }) {
  const parts = text.split("\n\n");
  const first = parts.slice(0, FIRST_PARAGRAPHS);
  const rest = parts.slice(FIRST_PARAGRAPHS);
  const p = (s: string, i: number) =>
    s === "Notes" ? (
      <p key={i} className="pt-1 text-xs font-semibold text-slate-600">{t("staff.notes")}</p>
    ) : (
      <p key={i} className={/^\[\d+\] /.test(s) ? "text-xs text-slate-500" : undefined}>{s}</p>
    );
  return (
    <blockquote className="mt-1 space-y-2 border-l-2 border-slate-300 pl-3 text-sm leading-relaxed text-slate-700">
      {first.map(p)}
      {rest.length > 0 && (
        <details>
          <summary className="cursor-pointer text-xs text-slate-600 underline">
            {t("staff.readMore", { count: rest.length })}
          </summary>
          <div className="mt-2 space-y-2">{rest.map((s, i) => p(s, FIRST_PARAGRAPHS + i))}</div>
        </details>
      )}
    </blockquote>
  );
}

export default function StaffAnalysisBox({ analysis }: { analysis: StaffAnalysisExcerpt }) {
  const when = analysis.analysis_date ? formatDate(analysis.analysis_date) : t("staff.undated");
  const committee = analysis.committee ?? t("staff.committeeUnknown");
  return (
    <section aria-labelledby="staff-analysis" className="mt-5">
      <h2 id="staff-analysis" className="text-sm font-semibold text-ledger-900">{t("staff.heading")}</h2>
      <div className="mt-2 rounded border border-slate-200 p-3">
        <p className="text-xs text-slate-500">
          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-700">{t("staff.badge")}</span>{" "}
          {t("staff.attribution", { committee, date: when })}{" "}
          <a href={analysis.source_url} className="underline hover:text-slate-700">{t("staff.pdf")}</a>
        </p>
        {!analysis.is_latest && (
          <p className="mt-1 text-xs text-slate-500">{t("staff.notLatest", { count: analysis.analyses_count })}</p>
        )}
        {analysis.effect && (
          <>
            <h3 className="mt-3 text-xs font-semibold text-slate-700">{t("staff.effect")}</h3>
            <Paragraphs text={analysis.effect} />
          </>
        )}
        {analysis.fiscal && (
          <>
            <h3 className="mt-3 text-xs font-semibold text-slate-700">{t("staff.fiscal")}</h3>
            <Paragraphs text={analysis.fiscal} />
          </>
        )}
        {analysis.truncated && <p className="mt-2 text-xs text-slate-500">{t("staff.truncated")}</p>}
        <p className="mt-2 text-[11px] text-slate-500">{t("staff.footer")}</p>
      </div>
    </section>
  );
}
