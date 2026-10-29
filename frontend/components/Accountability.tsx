import Link from "next/link";
import type { BillDetail, CorrectionOut, ResponseOut } from "@/lib/types";
import {
  CATEGORY_NAMES, CHANGE_TYPE_NAMES, changeLabel, correctionNote, forTarget, type TargetAccountability,
} from "@/lib/accountability";
import { t, tRich } from "@/lib/i18n";
import { LAYER_META, formatDate } from "@/lib/layers";

/** Correction process, step 4 (Notion spec): labels on the affected block,
 *  responses under the record they answer, and the bill's full history of
 *  corrections. Server-rendered; nothing here is hidden behind a script.
 *  Disputed statements stay up with a label -- never withheld (decision 2). */

function ResponseBlock({ r }: { r: ResponseOut }) {
  return (
    <div className="mt-2 rounded border-l-2 border-ledger-900 bg-slate-50 px-2 py-1.5 text-sm">
      <p className="text-xs font-medium text-ledger-900">
        {tRich("acct.response.header", {
          name: r.responder_name,
          role: r.responder_role ? (
            <span className="font-normal text-slate-600">{t("acct.response.role", { role: r.responder_role })}</span>
          ) : null,
          date: formatDate(r.received_at),
        })}
      </p>
      <p className="mt-0.5 whitespace-pre-line text-slate-700">{r.text}</p>
      {r.full_text_url && (
        <a href={r.full_text_url} target="_blank" rel="noreferrer" className="text-xs text-sunshine-700 underline">
          {t("acct.response.full")}
        </a>
      )}
      <p className="mt-0.5 text-[11px] text-slate-500">
        {t("acct.response.note", { via: r.verified_via })}
      </p>
    </div>
  );
}

/** Inline, on the block or record itself. Renders nothing when there's
 *  nothing to say. `withResponses={false}` for the page header, where the
 *  bill-level responses would repeat what CorrectionsSection shows. */
export function AccountabilityNotes({ items, withResponses = true }: { items: TargetAccountability; withResponses?: boolean }) {
  const current = withResponses ? items.responses.filter((r) => !r.superseded_by_id) : [];
  if (items.disputes.length === 0 && items.corrections.length === 0 && current.length === 0) return null;
  return (
    <div className="mt-2 space-y-1">
      {items.disputes.map((d) => (
        <p key={d.flag_id} className="text-xs">
          <a
            href="#corrections"
            className="rounded bg-amber-100 px-1.5 py-0.5 font-medium text-amber-900 underline decoration-amber-900/40"
          >
            {t("acct.disputed")}
          </a>
          <span className="ml-1.5 text-slate-600">
            {t("acct.disputed.since", { date: formatDate(d.disputed_since), category: CATEGORY_NAMES[d.category] ?? d.category })}
          </span>
        </p>
      ))}
      {items.corrections.map((c) => {
        const note = correctionNote(c);
        return (
          <p key={c.id} className="text-xs">
            <a
              href={`#correction-${c.id}`}
              className="rounded bg-slate-200 px-1.5 py-0.5 font-medium text-ledger-900 underline decoration-ledger-900/40"
            >
              {changeLabel(c)}
            </a>
            {note && <span className="ml-1.5 text-slate-600">{note}</span>}
          </p>
        );
      })}
      {current.map((r) => (
        <ResponseBlock key={r.id} r={r} />
      ))}
    </div>
  );
}

const TRIGGER_KEYS = {
  challenge: "acct.trigger.challenge",
  internal_review: "acct.trigger.internal_review",
  source_change: "acct.trigger.source_change",
  methodology_change: "acct.trigger.methodology_change",
} as const satisfies Record<CorrectionOut["trigger"], string>;

const OBJECT_KEYS = {
  bill: "acct.object.bill",
  page_copy: "acct.object.page_copy",
  claim: "acct.object.claim",
  amendment: "acct.object.amendment",
  vote: "acct.object.vote",
} as const;

function describeTarget(bill: BillDetail, objectType: string, objectId: string | null): string {
  if (objectType === "bill_layer" && objectId) {
    for (const [layer, blocks] of Object.entries(bill.layers)) {
      for (const b of blocks ?? []) {
        const versions = [b.current, ...b.earlier_versions];
        if (versions.some((v) => v?.id === objectId)) {
          const title = LAYER_META[layer as keyof typeof LAYER_META]?.title ?? "Who it affects";
          return t("acct.object.layerBlock", { title });
        }
      }
    }
    return t("acct.object.analysisBlock");
  }
  return t(OBJECT_KEYS[objectType as keyof typeof OBJECT_KEYS] ?? "acct.object.bill");
}

function originText(c: CorrectionOut): string | null {
  if (c.origin === "sunshine_ledger_ai") {
    return c.was_reviewed ? t("acct.origin.aiReviewed") : t("acct.origin.aiUnreviewed");
  }
  if (c.origin === "legislative_staff") return t("acct.origin.staff");
  if (c.origin === "bill_text") return t("acct.origin.billText");
  return null;
}

function CorrectionEntry({ bill, c }: { bill: BillDetail; c: CorrectionOut }) {
  const origin = originText(c);
  return (
    <li id={`correction-${c.id}`} className="scroll-mt-4 rounded-md border border-slate-200 p-2">
      <p className="text-sm">
        <span className="font-medium text-ledger-900">{changeLabel(c)}</span>
        <span className="text-slate-600">
          {t("acct.entry.change", {
            type: CHANGE_TYPE_NAMES[c.change_type],
            severity: c.severity,
            target: describeTarget(bill, c.object_type, c.object_id),
          })}
        </span>
      </p>
      <p className="mt-1 text-sm text-slate-700">{c.explanation}</p>
      {(c.prior_text || c.current_text) && (
        <details className="mt-1 text-xs text-slate-600" open={c.severity !== "minor"}>
          <summary className="cursor-pointer underline">{t("acct.entry.beforeAfter")}</summary>
          {c.prior_text && (
            <div className="mt-1">
              <p className="font-medium">
                {c.prior_version ? t("acct.entry.earlierVersion", { version: c.prior_version }) : t("acct.entry.earlier")}
              </p>
              <del className="block whitespace-pre-line bg-red-50 px-1 text-slate-700">{c.prior_text}</del>
            </div>
          )}
          {c.current_text && (
            <div className="mt-1">
              <p className="font-medium">
                {c.change_type === "retraction"
                  ? c.current_version
                    ? t("acct.entry.nowSaysVersion", { version: c.current_version })
                    : t("acct.entry.nowSays")
                  : c.current_version
                    ? t("acct.entry.correctedVersion", { version: c.current_version })
                    : t("acct.entry.corrected")}
              </p>
              <ins className="block whitespace-pre-line bg-green-50 px-1 no-underline text-slate-700">{c.current_text}</ins>
            </div>
          )}
        </details>
      )}
      {c.evidence_links.length > 0 && (
        <ul className="mt-1 text-xs text-slate-600">
          {c.evidence_links.map((e, i) => (
            <li key={i}>
              {e.role
                ? t("acct.entry.evidenceRole", { role: `${e.role[0].toUpperCase()}${e.role.slice(1)}` })
                : t("acct.entry.evidence")}
              <a href={e.url} target="_blank" rel="noreferrer" className="text-sunshine-700 underline">
                {e.note || e.url}
              </a>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-1 text-[11px] text-slate-500">
        {t(TRIGGER_KEYS[c.trigger])}
        {origin && t("acct.entry.origin", { text: origin })}
        {t("acct.entry.decidedBy", { label: c.decided_by_label })}
        {c.methodology_version && t("acct.entry.method", { version: c.methodology_version })}
      </p>
    </li>
  );
}

/** The bill's own corrections history: open disputes, every correction
 *  (Minor ones too, oldest first so it reads in order), and all responses
 *  including superseded ones. Absent when there's nothing to show. */
export function CorrectionsSection({ bill }: { bill: BillDetail }) {
  const disputes = bill.disputes ?? [];
  const corrections = bill.corrections ?? [];
  const responses = bill.responses ?? [];
  if (disputes.length === 0 && corrections.length === 0 && responses.length === 0) return null;
  const billLevel = forTarget(bill, "bill", []);
  const superseded = responses.filter((r) => r.superseded_by_id);
  return (
    <section id="corrections" aria-labelledby="corrections-heading" className="mt-5 scroll-mt-4">
      <h2 id="corrections-heading" className="text-sm font-semibold text-ledger-900">
        {t("acct.section.title")}
      </h2>
      <p className="text-xs text-slate-500">
        {tRich("acct.section.intro", {
          link: (
            <Link href="/methodology#corrections" className="underline hover:text-slate-700">
              {t("acct.section.how")}
            </Link>
          ),
        })}
      </p>
      {disputes.length > 0 && (
        <>
          <h3 className="mt-3 text-xs font-semibold text-slate-700">{t("acct.section.underReview")}</h3>
          <ul className="mt-1 space-y-1 text-sm text-slate-700">
            {disputes.map((d) => (
              <li key={d.flag_id}>
                <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-900">
                  {t("acct.disputed")}
                </span>{" "}
                {t("acct.section.dispute", {
                  target: describeTarget(bill, d.object_type, d.object_id),
                  category: CATEGORY_NAMES[d.category] ?? d.category,
                  date: formatDate(d.disputed_since),
                })}
              </li>
            ))}
          </ul>
        </>
      )}
      {corrections.length > 0 && (
        <>
          <h3 className="mt-3 text-xs font-semibold text-slate-700">{t("acct.section.corrections")}</h3>
          <ul className="mt-1 space-y-2">
            {corrections.map((c) => (
              <CorrectionEntry key={c.id} bill={bill} c={c} />
            ))}
          </ul>
        </>
      )}
      {billLevel.responses.filter((r) => !r.superseded_by_id).length > 0 && (
        <>
          <h3 className="mt-3 text-xs font-semibold text-slate-700">{t("acct.section.responses")}</h3>
          {billLevel.responses.filter((r) => !r.superseded_by_id).map((r) => (
            <ResponseBlock key={r.id} r={r} />
          ))}
        </>
      )}
      {superseded.length > 0 && (
        <details className="mt-2 text-xs text-slate-500">
          <summary className="cursor-pointer underline">
            {t("acct.section.superseded", { count: superseded.length })}
          </summary>
          {superseded.map((r) => (
            <ResponseBlock key={r.id} r={r} />
          ))}
        </details>
      )}
      <p className="mt-2 text-xs">
        <Link href="/corrections" className="text-sunshine-700 underline">{t("acct.section.all")}</Link>
      </p>
    </section>
  );
}
