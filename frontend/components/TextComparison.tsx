"use client";

import { Fragment, useMemo, useState } from "react";

import { t } from "@/lib/i18n";
import { fetchFiledText } from "@/lib/api";
import { lawAsAmended } from "@/lib/changeMarkers";
import { MAX_COMPARE_CHARS, compareTexts, type CompareBlock } from "@/lib/textCompare";
import type { TextVersion, TextVersions } from "@/lib/types";

function describe(v: TextVersion, fallback: string): string {
  const label = v.version_type ?? fallback;
  return v.version_date ? `${label}, ${v.version_date}` : label;
}

function SameBlock({ clauses }: { clauses: string[] }) {
  const [open, setOpen] = useState(false);
  if (open || clauses.length <= 2) {
    return <p className="text-slate-500">{clauses.join(" ")}</p>;
  }
  return (
    <button
      type="button"
      onClick={() => setOpen(true)}
      className="block text-left text-xs italic text-slate-500 underline hover:text-slate-700"
    >
      … {t("compare.unchanged", { count: clauses.length })} …
    </button>
  );
}

function ChangedBlock({ block }: { block: Extract<CompareBlock, { kind: "changed" }> }) {
  return (
    <p className="text-slate-800">
      {block.parts.map((part, i) =>
        part.added ? (
          <ins key={i} className="bg-emerald-100 text-emerald-900 underline decoration-emerald-600">
            {part.value}
          </ins>
        ) : part.removed ? (
          <del key={i} className="text-red-700 decoration-red-500">
            {part.value}
          </del>
        ) : (
          <Fragment key={i}>{part.value}</Fragment>
        ),
      )}
    </p>
  );
}

/** "How the text changed": the bill as filed vs its current text. Collapsed
 *  by default; the filed text is only fetched when someone opens it. Plain
 *  comparison of the official texts -- no description of what the changes
 *  mean. Rewrites get side-by-side texts, and very large bills get links
 *  to the official versions instead of a comparison a phone can't handle. */
export default function TextComparison({
  entityId,
  versions,
  currentText,
}: {
  entityId: string;
  versions: TextVersions;
  currentText: string;
}) {
  const [open, setOpen] = useState(false);
  const [filedText, setFiledText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const tooLarge = Math.max(versions.filed.characters, versions.current.characters) > MAX_COMPARE_CHARS;
  const comparison = useMemo(
    () => (filedText === null ? null : compareTexts(filedText, currentText)),
    [filedText, currentText],
  );

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && filedText === null) {
      setError(null);
      fetchFiledText(entityId)
        .then((f) => setFiledText(f.text))
        .catch(() => setError(t("compare.loadError")));
    }
  };

  const links = (
    <>
      {versions.filed.url && (
        <a href={versions.filed.url} target="_blank" rel="noreferrer" className="underline">
          {t("compare.filedLink")}
        </a>
      )}
      {versions.filed.url && versions.current.url && " · "}
      {versions.current.url && (
        <a href={versions.current.url} target="_blank" rel="noreferrer" className="underline">
          {t("compare.currentLink")}
        </a>
      )}
    </>
  );

  return (
    <section className="mt-4" aria-labelledby="text-changes-heading">
      <h2 id="text-changes-heading" className="text-sm font-semibold text-ledger-900">
        {t("compare.title")}
      </h2>
      <p className="text-sm text-slate-700">
        {t("compare.versions", {
          filed: describe(versions.filed, t("compare.filedFallback")),
          current: describe(versions.current, t("compare.currentFallback")),
        })}
      </p>

      {tooLarge ? (
        <p className="mt-1 text-xs text-slate-500">
          {t("compare.tooLarge")} {links}
        </p>
      ) : (
        <>
          <button
            type="button"
            onClick={toggle}
            aria-expanded={open}
            aria-controls="text-comparison"
            className="mt-1 text-xs font-medium text-sunshine-700 underline hover:text-sunshine-800"
          >
            {open ? t("compare.hide") : t("compare.show")}
          </button>

          {open && (
            <div id="text-comparison" className="mt-2 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm">
              {error && <p className="text-red-700">{error}</p>}
              {!error && !comparison && <p className="text-slate-500">{t("compare.loading")}</p>}
              {comparison && (
                <>
                  <p className="font-medium text-ledger-900">
                    {t("compare.percent", { pct: Math.round((1 - comparison.similarity) * 100) })}
                  </p>
                  <p className="mb-3 text-[11px] text-slate-500">
                    {t("compare.method")} {links}
                  </p>
                  {comparison.rewritten ? (
                    <>
                      <p className="mb-2 text-slate-700">
                        {t("compare.rewritten")}
                      </p>
                      <div className="grid gap-3 md:grid-cols-2">
                        {[
                          { title: t("compare.asFiled"), text: lawAsAmended(filedText ?? "") },
                          { title: t("compare.current"), text: lawAsAmended(currentText) },
                        ].map((col) => (
                          <div key={col.title}>
                            <h3 className="text-xs font-semibold text-ledger-900">{col.title}</h3>
                            <p
                              tabIndex={0}
                              className="max-h-96 overflow-y-auto whitespace-pre-wrap rounded border border-slate-200 bg-white p-2 text-xs"
                            >
                              {col.text}
                            </p>
                          </div>
                        ))}
                      </div>
                    </>
                  ) : (
                    <div className="space-y-2 leading-relaxed">
                      {comparison.blocks.map((block, i) =>
                        block.kind === "same" ? (
                          <SameBlock key={i} clauses={block.clauses} />
                        ) : (
                          <ChangedBlock key={i} block={block} />
                        ),
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
