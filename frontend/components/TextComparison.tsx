"use client";

import { Fragment, useMemo, useState } from "react";

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
      … {clauses.length} unchanged passages (show) …
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
        .catch(() => setError("Couldn't load the filed text. Try again later."));
    }
  };

  const links = (
    <>
      {versions.filed.url && (
        <a href={versions.filed.url} target="_blank" rel="noreferrer" className="underline">
          filed version ↗
        </a>
      )}
      {versions.filed.url && versions.current.url && " · "}
      {versions.current.url && (
        <a href={versions.current.url} target="_blank" rel="noreferrer" className="underline">
          current version ↗
        </a>
      )}
    </>
  );

  return (
    <section className="mt-4" aria-labelledby="text-changes-heading">
      <h2 id="text-changes-heading" className="text-sm font-semibold text-ledger-900">
        How the text changed
      </h2>
      <p className="text-sm text-slate-700">
        Filed: {describe(versions.filed, "filed version")} · Current: {describe(versions.current, "current version")}
      </p>

      {tooLarge ? (
        <p className="mt-1 text-xs text-slate-500">
          Too long to compare here. Official texts: {links}
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
            {open ? "Hide the comparison" : "Compare the filed and current text"}
          </button>

          {open && (
            <div id="text-comparison" className="mt-2 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm">
              {error && <p className="text-red-700">{error}</p>}
              {!error && !comparison && <p className="text-slate-500">Loading the filed text…</p>}
              {comparison && (
                <>
                  <p className="font-medium text-ledger-900">
                    About {Math.round((1 - comparison.similarity) * 100)}% of the wording changed.
                  </p>
                  <p className="mb-3 text-[11px] text-slate-500">
                    Compared by Sunshine Ledger from the official texts, as the law would read (the bill&apos;s own
                    strike-through and underlining resolved; line breaks ignored). Added wording is underlined,
                    removed wording struck through. Official texts: {links}
                  </p>
                  {comparison.rewritten ? (
                    <>
                      <p className="mb-2 text-slate-700">
                        Substantially rewritten from the filed version, so the two texts are shown side by side.
                      </p>
                      <div className="grid gap-3 md:grid-cols-2">
                        {[
                          { title: "As filed", text: lawAsAmended(filedText ?? "") },
                          { title: "Current", text: lawAsAmended(currentText) },
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
