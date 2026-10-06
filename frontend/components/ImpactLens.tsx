"use client";

import { useEffect, useMemo, useState } from "react";
import { fetchImpactLens } from "@/lib/api";
import {
  cleanAnswers,
  matchBill,
  toLensBill,
  type Answers,
  type ImpactLensResponse,
  type LensQuestion,
  type QuestionKey,
  type ResultKind,
} from "@/lib/impactLens";

/** "Do you want to see if you may be impacted?" Optional and opt-in: nothing is
 *  asked or fetched until the reader says yes.
 *
 *  Privacy (Product & Trust Foundation, Impact Lens boundary, agreed 2026-10-05):
 *  answers stay in this browser (sessionStorage), are never sent to the server,
 *  and a visible control clears them. Only the bill's criteria are fetched.
 *  The result is relevance, not legal advice, and never changes the record.
 */

const STORAGE_KEY = "impactLens.answers.v1";
const NONE = "none_of_these";

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

const SCOPE: Record<ResultKind, string> = {
  applies: "This is based on the provisions below and the answers you gave.",
  may_affect: "This is a possible, indirect effect based on the answers you gave, not an established fact.",
  ambiguous: "The text of the bill leaves a question open that decides whether it reaches you. We do not guess.",
  cant_determine: "We do not have enough, from the bill or from your answers, to say either way.",
  does_not_appear:
    "Based only on the provisions we have analyzed and the answers you gave. This is not a guarantee that the bill has no effect on you.",
  everyone_only: "Every provision we found applies to everyone.",
};

const input = "h-4 w-4 accent-sunshine-700";
const field = "mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm focus:border-sunshine-500 focus:outline-none focus:ring-1 focus:ring-sunshine-500";

function QuestionBlock({
  q,
  value,
  onAnswer,
}: {
  q: LensQuestion;
  value: string | undefined;
  onAnswer: (key: QuestionKey, v: string) => void;
}) {
  if (q.options.length > 8) {
    const id = `lens-${q.key}`;
    return (
      <div className="mt-3">
        <label htmlFor={id} className="block text-sm font-medium text-ledger-900">
          {q.question}
        </label>
        <select id={id} className={field} value={value ?? ""} onChange={(e) => e.target.value && onAnswer(q.key, e.target.value)}>
          <option value="">Choose one</option>
          {q.options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
    );
  }
  return (
    <fieldset className="mt-3">
      <legend className="text-sm font-medium text-ledger-900">{q.question}</legend>
      <div className="mt-1 space-y-1">
        {q.options.map((o) => (
          <label key={o.value} className="flex items-center gap-2 text-sm text-ledger-800">
            <input type="radio" name={`lens-${q.key}`} className={input} checked={value === o.value} onChange={() => onAnswer(q.key, o.value)} />
            {o.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export default function ImpactLens({ billEntityId }: { billEntityId: string }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<ImpactLensResponse | null>(null);
  const [error, setError] = useState(false);
  const [answers, setAnswers] = useState<Answers>({});

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

  const result = useMemo(() => (data?.available ? matchBill(toLensBill(data), answers) : null), [data, answers]);
  const byKey = useMemo(() => new Map((data?.questions ?? []).map((q) => [q.key, q])), [data]);

  function answer(key: QuestionKey, v: string) {
    const next: Answers = { ...answers, [key]: v };
    // A different county invalidates a municipality chosen under the old one.
    if (key === "county") delete next.municipality;
    setAnswers(next);
    writeAnswers(next);
  }
  function change(key: QuestionKey) {
    const next = { ...answers };
    delete next[key];
    if (key === "county") delete next.municipality;
    setAnswers(next);
    writeAnswers(next);
  }
  function clearAll() {
    setAnswers({});
    forgetAnswers();
  }

  const answeredChips = (["role", "county", "municipality", "property_type"] as QuestionKey[]).filter((k) => answers[k] !== undefined);
  const labelFor = (k: QuestionKey, v: string) => byKey.get(k)?.options.find((o) => o.value === v)?.label ?? v;
  // "Role: Local Government", but "Duval County" rather than "County: Duval County".
  const describe = (k: QuestionKey, v: string) => {
    const option = labelFor(k, v);
    const name = byKey.get(k)?.label ?? k;
    return option.toLowerCase().includes(name.toLowerCase()) ? option : `${name}: ${option}`;
  };

  return (
    <section className="mt-4 rounded-lg border border-slate-200 bg-white p-4" aria-labelledby="impact-lens-heading">
      <h2 id="impact-lens-heading" className="text-sm font-semibold text-ledger-900">
        Does this affect you?
      </h2>

      {!open && (
        <div className="mt-2">
          <p className="text-sm text-slate-700">Do you want to see if you may be impacted?</p>
          <p className="mt-1 text-xs text-slate-500">Optional. We ask only what this bill needs. Your answers stay in this browser.</p>
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="mt-2 rounded-md border border-sunshine-700 px-3 py-1.5 text-sm font-medium text-sunshine-700 hover:bg-sunshine-50"
          >
            Yes, check
          </button>
        </div>
      )}

      {open && error && <p className="mt-2 text-sm text-red-700">We could not load this bill&apos;s questions. Try again later.</p>}
      {open && !error && !data && <p className="mt-2 text-sm text-slate-600">Loading…</p>}
      {open && data && !data.available && (
        <p className="mt-2 text-sm text-slate-700">{data.unavailable_reason ?? "This bill has not been analyzed for this yet."}</p>
      )}

      {open && data?.available && result && (
        <div className="mt-2">
          {answeredChips.length > 0 && (
            <p className="text-xs text-slate-600">
              Your answers:{" "}
              {answeredChips.map((k, i) => (
                <span key={k}>
                  {i > 0 && " · "}
                  {byKey.get(k)?.label ?? k}: <strong>{labelFor(k, answers[k] as string)}</strong>{" "}
                  <button type="button" className="underline text-sunshine-700" onClick={() => change(k)} aria-label={`Change ${byKey.get(k)?.label ?? k}`}>
                    change
                  </button>
                </span>
              ))}
            </p>
          )}

          {result.ask.length > 0 &&
            result.ask.slice(0, 1).map((key) => {
              const q = byKey.get(key);
              return q ? <QuestionBlock key={key} q={q} value={answers[key]} onAnswer={answer} /> : null;
            })}

          <div role="status" aria-live="polite" className={`mt-3 rounded-md border px-3 py-2 ${TONE[result.result]}`}>
            <p className="text-base font-semibold">{result.label}</p>
            <p className="mt-0.5 text-xs">{SCOPE[result.result]}</p>
            {result.ask.length > 0 && <p className="mt-0.5 text-xs">Answer the question above to narrow this down.</p>}
          </div>

          {result.ambiguity && (
            <p className="mt-2 text-sm text-slate-800">
              <strong>The open question:</strong> {result.ambiguity.question} <q className="italic">{result.ambiguity.quote}</q>
            </p>
          )}

          {result.why.length > 0 && result.result !== "ambiguous" && (
            <details className="mt-2 text-sm" open>
              <summary className="cursor-pointer font-medium text-ledger-900">Why we say this</summary>
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
              <p className="font-medium text-ledger-900">Applies to everyone</p>
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
            <p className="mt-3 text-xs text-slate-600">Automatically mapped, not yet reviewed by a person.</p>
          )}
          {!data.complete && (
            <p className="mt-1 text-xs text-slate-600">
              This list of provisions may not be complete: {data.incomplete_reasons.join(" ")}
            </p>
          )}
          <p className="mt-3 text-xs text-slate-500">
            This is about relevance, not legal or financial advice, and it does not change the bill&apos;s record.{" "}
            <button type="button" className="underline text-sunshine-700" onClick={clearAll}>
              Clear my answers
            </button>
          </p>
        </div>
      )}
    </section>
  );
}
