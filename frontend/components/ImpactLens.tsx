"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { fetchImpactLens } from "@/lib/api";
import { t, type MessageKey } from "@/lib/i18n";
import {
  QUESTION_KEYS,
  cleanAnswers,
  matchBill,
  toLensBill,
  type Answers,
  type ImpactLensResponse,
  type LensQuestion,
  type QuestionKey,
  type ResultKind,
  placesOf,
} from "@/lib/impactLens";

/** "Do you want to see if you may be impacted?" Optional and opt-in: nothing is
 *  asked or fetched until the reader says yes.
 *
 *  Privacy (Product & Trust Foundation, Impact Lens boundary, agreed 2026-10-05):
 *  answers stay in this browser (sessionStorage), are never sent to the server,
 *  and a visible control clears them. Only the bill's criteria are fetched.
 *  The result is relevance, not legal advice, and never changes the record.
 */

const STORAGE_KEY = "impactLens.answers.v2";
/** The v1 key held only the residence answers. Cleared with the rest so it does not linger. */
const OLD_STORAGE_KEY = "impactLens.answers.v1";

/** A municipality answer only makes sense under the county answered with it. */
const CITY_OF: Partial<Record<QuestionKey, QuestionKey>> = {
  county: "municipality",
  property_county: "property_municipality",
  business_county: "business_municipality",
};

function readAnswers(): Answers {
  try {
    return cleanAnswers(JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) ?? "null"));
  } catch {
    return {};
  }
}
function writeAnswers(a: Answers) {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(a));
  } catch {
    /* private mode or blocked: the lens still works for this page view */
  }
}
function forgetAnswers() {
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
    window.sessionStorage.removeItem(OLD_STORAGE_KEY);
  } catch {
    /* nothing to clear */
  }
}

const TONE: Record<ResultKind, string> = {
  applies: "border-emerald-300 bg-emerald-50 text-emerald-900",
  may_affect: "border-amber-300 bg-amber-50 text-amber-900",
  ambiguous: "border-amber-300 bg-amber-50 text-amber-900",
  cant_determine: "border-slate-300 bg-slate-50 text-slate-800",
  does_not_appear: "border-slate-300 bg-slate-50 text-slate-800",
  everyone_only: "border-emerald-300 bg-emerald-50 text-emerald-900",
};

const SCOPE: Record<ResultKind, MessageKey> = {
  applies: "lens.scope.applies",
  may_affect: "lens.scope.may_affect",
  ambiguous: "lens.scope.ambiguous",
  cant_determine: "lens.scope.cant_determine",
  does_not_appear: "lens.scope.does_not_appear",
  everyone_only: "lens.scope.everyone_only",
};

const input = "h-4 w-4 accent-sunshine-700";
const field = "mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm focus:border-sunshine-500 focus:outline-none focus:ring-1 focus:ring-sunshine-500";

/** A choice is only committed by the Continue button: arrowing through radios or a
 *  list must not change the page by itself (WCAG 3.2.2, On Input). */
function QuestionBlock({
  q,
  value,
  onAnswer,
}: {
  q: LensQuestion;
  value: string | undefined;
  onAnswer: (key: QuestionKey, v: string) => void;
}) {
  const [choice, setChoice] = useState(value ?? "");
  const next = (
    <button
      type="button"
      disabled={!choice}
      onClick={() => choice && onAnswer(q.key, choice)}
      className="mt-2 rounded-md border border-sunshine-700 px-3 py-1.5 text-sm font-medium text-sunshine-700 hover:bg-sunshine-50 disabled:cursor-not-allowed disabled:opacity-50"
    >
      Continue
    </button>
  );
  if (q.options.length > 8) {
    const id = `lens-${q.key}`;
    return (
      <div className="mt-3" data-lens-question>
        <label htmlFor={id} className="block text-sm font-medium text-ledger-900">
          {q.question}
        </label>
        <select id={id} className={field} value={choice} onChange={(e) => setChoice(e.target.value)}>
          <option value="">{t("lens.chooseOne")}</option>
          {q.options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        {next}
      </div>
    );
  }
  return (
    <fieldset className="mt-3" data-lens-question>
      <legend className="text-sm font-medium text-ledger-900">{q.question}</legend>
      <div className="mt-1 space-y-1">
        {q.options.map((o) => (
          <label key={o.value} className="flex items-center gap-2 text-sm text-ledger-800">
            <input type="radio" name={`lens-${q.key}`} className={input} checked={choice === o.value} onChange={() => setChoice(o.value)} />
            {o.label}
          </label>
        ))}
      </div>
      {next}
    </fieldset>
  );
}

export default function ImpactLens({ billEntityId }: { billEntityId: string }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<ImpactLensResponse | null>(null);
  const [error, setError] = useState(false);
  const [answers, setAnswers] = useState<Answers>({});
  // Keyboard and screen-reader users lose their place when the control they used
  // unmounts (the button that opens the lens, an answered question). After each
  // such step focus moves to the next question, else to the result.
  const rootRef = useRef<HTMLElement>(null);
  const focusPending = useRef(false);
  // A property or workplace county the reader is adding to the one already given.
  const [adding, setAdding] = useState<QuestionKey | null>(null);

  useEffect(() => {
    if (!open || data || error) return;
    let cancelled = false;
    setAnswers(readAnswers());
    fetchImpactLens(billEntityId)
      .then((d) => !cancelled && setData(d))
      .catch(() => !cancelled && setError(true));
    return () => {
      cancelled = true;
    };
  }, [open, data, error, billEntityId]);

  useEffect(() => {
    if (!focusPending.current || !open || (!data && !error)) return;
    focusPending.current = false;
    const root = rootRef.current;
    const control = root?.querySelector<HTMLElement>("[data-lens-question] input, [data-lens-question] select");
    const target = control ?? root?.querySelector<HTMLElement>("[data-lens-result]") ?? root?.querySelector<HTMLElement>("h2");
    target?.focus();
  });

  const result = useMemo(() => (data?.available ? matchBill(toLensBill(data), answers) : null), [data, answers]);
  const byKey = useMemo(() => new Map((data?.questions ?? []).map((q) => [q.key, q])), [data]);

  function answer(key: QuestionKey, v: string) {
    const next: Answers = { ...answers, [key]: v };
    // A different county invalidates a municipality chosen under the old one.
    const city = CITY_OF[key];
    if (city) delete next[city];
    setAnswers(next);
    writeAnswers(next);
    focusPending.current = true;
  }
  /** Add one more county of the same kind (rentals in two counties). Capped, de-duplicated. */
  function addPlace(key: QuestionKey, v: string) {
    const names = [...new Set([...placesOf(answers[key]), v])].slice(0, 10);
    const next = { ...answers, [key]: names.length === 1 ? names[0] : names } as Answers;
    setAnswers(next);
    writeAnswers(next);
    setAdding(null);
    focusPending.current = true;
  }
  function change(key: QuestionKey) {
    const next = { ...answers };
    delete next[key];
    const city = CITY_OF[key];
    if (city) delete next[city];
    setAnswers(next);
    writeAnswers(next);
    focusPending.current = true;
  }
  /** Answer a property or business county question with the reader's residence county
   *  (and city, if they gave one). */
  function sameAsResidence(key: QuestionKey) {
    if (answers.county === undefined) return;
    const next: Answers = { ...answers, [key]: answers.county } as Answers;
    const city = CITY_OF[key];
    if (city) {
      if (answers.municipality !== undefined) (next as Record<string, unknown>)[city] = answers.municipality;
      else delete next[city];
    }
    setAnswers(next);
    writeAnswers(next);
    focusPending.current = true;
  }
  function clearAll() {
    setAnswers({});
    setAdding(null);
    forgetAnswers();
    focusPending.current = true;
  }

  const answeredChips = QUESTION_KEYS.filter((k) => answers[k] !== undefined);
  const labelFor = (k: QuestionKey, v: string) => byKey.get(k)?.options.find((o) => o.value === v)?.label ?? v;
  // "Role: Local Government", but "Duval County" rather than "County: Duval County".
  const describe = (k: QuestionKey, v: string) => {
    const option = labelFor(k, v);
    const name = byKey.get(k)?.label ?? k;
    return option.toLowerCase().includes(name.toLowerCase()) ? option : `${name}: ${option}`;
  };

  return (
    <section ref={rootRef} className="mt-4 rounded-lg border border-slate-200 bg-white p-4" aria-labelledby="impact-lens-heading">
      <h2 id="impact-lens-heading" tabIndex={-1} className="text-sm font-semibold text-ledger-900 focus:outline-none">
        {t("lens.title")}
      </h2>

      {!open && (
        <div className="mt-2">
          <p className="text-sm text-slate-700">{t("lens.prompt")}</p>
          <p className="mt-1 text-xs text-slate-500">{t("lens.optional")}</p>
          <button
            type="button"
            onClick={() => {
              focusPending.current = true;
              setOpen(true);
            }}
            className="mt-2 rounded-md border border-sunshine-700 px-3 py-1.5 text-sm font-medium text-sunshine-700 hover:bg-sunshine-50"
          >
            {t("lens.yesCheck")}
          </button>
        </div>
      )}

      {open && error && <p className="mt-2 text-sm text-red-700">{t("lens.loadError")}</p>}
      {open && !error && !data && <p className="mt-2 text-sm text-slate-600">{t("lens.loading")}</p>}
      {open && data && !data.available && (
        <p className="mt-2 text-sm text-slate-700">{data.unavailable_reason ?? t("lens.notAnalyzed")}</p>
      )}

      {open && data?.available && result && (
        <div className="mt-2">
          {answeredChips.length > 0 && (
            <p className="text-xs text-slate-600">
              {t("lens.yourAnswers")}{" "}
              {answeredChips.map((k, i) => (
                <span key={k}>
                  {i > 0 && " · "}
                  {byKey.get(k)?.label ?? k}: <strong>{placesOf(answers[k]).map((v) => labelFor(k, v)).join(", ")}</strong>{" "}
                  <button type="button" className="underline text-sunshine-700" onClick={() => change(k)} aria-label={t("lens.changeAria", { label: byKey.get(k)?.label ?? k })}>
                    {t("lens.change")}
                  </button>
                  {(k === "property_county" || k === "business_county") && placesOf(answers[k]).length < 10 && (
                    <>
                      {" "}
                      <button type="button" className="underline text-sunshine-700" onClick={() => { setAdding(k); focusPending.current = true; }} aria-label={t("lens.addAnotherAria", { label: byKey.get(k)?.label ?? k })}>
                        {t("lens.addAnother")}
                      </button>
                    </>
                  )}
                </span>
              ))}
            </p>
          )}

          {adding && byKey.get(adding) && (
            <div>
              <QuestionBlock
                q={{ ...byKey.get(adding)!, options: byKey.get(adding)!.options.filter((o) => o.value !== "none_of_these" && !placesOf(answers[adding]).includes(o.value)) }}
                value={undefined}
                onAnswer={addPlace}
              />
              <button type="button" onClick={() => setAdding(null)} className="mt-1 text-sm underline text-sunshine-700">
                {t("lens.cancelAdd")}
              </button>
            </div>
          )}

          {!adding && result.ask.length > 0 &&
            result.ask.slice(0, 1).map((key) => {
              const q = byKey.get(key);
              if (!q) return null;
              // A property or workplace is often where the reader lives. If they have
              // already told us their county, let them reuse it rather than answer twice.
              // The question flow stores one place per kind; a list only comes from storage.
              const residence = placesOf(answers.county)[0];
              const canReuse = (key === "property_county" || key === "business_county") && residence !== undefined;
              return (
                <div key={key}>
                  <QuestionBlock q={q} value={placesOf(answers[key])[0]} onAnswer={answer} />
                  {canReuse && (
                    <button type="button" onClick={() => sameAsResidence(key)} className="mt-1 text-sm underline text-sunshine-700">
                      {t("lens.sameAsResidence", { place: q.options.find((o) => o.value === residence)?.label ?? residence })}
                    </button>
                  )}
                </div>
              );
            })}

          <div role="status" aria-live="polite" tabIndex={-1} data-lens-result className={`mt-3 rounded-md border px-3 py-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-sunshine-700 ${TONE[result.result]}`}>
            <p className="text-base font-semibold">{result.label}</p>
            <p className="mt-0.5 text-xs">{t(SCOPE[result.result])}</p>
            {result.ask.length > 0 && <p className="mt-0.5 text-xs">{t("lens.answerAbove")}</p>}
          </div>

          {result.ambiguity && (
            <p className="mt-2 text-sm text-slate-800">
              <strong>{t("lens.openQuestion")}</strong> {result.ambiguity.question} <q className="italic">{result.ambiguity.quote}</q>
            </p>
          )}

          {result.why.length > 0 && result.result !== "ambiguous" && (
            <details className="mt-2 text-sm" open>
              <summary className="cursor-pointer font-medium text-ledger-900">{t("lens.why")}</summary>
              <ol className="mt-1 list-decimal space-y-2 pl-5 text-slate-800">
                {result.why.map((w, i) => (
                  <li key={i}>
                    <span className="block text-xs text-slate-600">{w.circumstances.map((c) => describe(c.key, c.value)).join(" · ")}</span>
                    <q className="italic">{w.quote}</q>
                    <span className="block">{w.reasoning}</span>
                  </li>
                ))}
              </ol>
            </details>
          )}

          {result.everyone.length > 0 && result.result !== "everyone_only" && (
            <div className="mt-3 text-sm text-slate-800">
              <p className="font-medium text-ledger-900">{t("lens.appliesToEveryone")}</p>
              <ul className="mt-1 list-disc space-y-1 pl-5">
                {result.everyone.map((e) => (
                  <li key={e.index}>
                    <strong>{e.entry.group}:</strong> {e.entry.text} <q className="italic">{e.entry.quote}</q>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {(result.unreviewed && result.basis.length > 0) && (
            <p className="mt-3 text-xs text-slate-600">{t("lens.unreviewed")}</p>
          )}
          {!data.complete && (
            <p className="mt-1 text-xs text-slate-600">
              {t("lens.incomplete", { reasons: data.incomplete_reasons.join(" ") })}
            </p>
          )}
          <p className="mt-3 text-xs text-slate-500">
            {t("lens.disclaimer")}{" "}
            <button type="button" className="underline text-sunshine-700" onClick={clearAll}>
              {t("lens.clear")}
            </button>
          </p>
        </div>
      )}
    </section>
  );
}
