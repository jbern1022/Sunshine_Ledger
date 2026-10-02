import Link from "next/link";
import type { BillDetail, CorrectionOut, ResponseOut } from "@/lib/types";
import {
  CATEGORY_NAMES, CHANGE_TYPE_NAMES, changeLabel, correctionNote, forTarget, type TargetAccountability,
} from "@/lib/accountability";
import { LAYER_META, formatDate } from "@/lib/layers";

/** Correction process, step 4 (Notion spec): labels on the affected block,
 *  responses under the record they answer, and the bill's full history of
 *  corrections. Server-rendered; nothing here is hidden behind a script.
 *  Disputed statements stay up with a label -- never withheld (decision 2). */

function ResponseBlock({ r }: { r: ResponseOut }) {
  return (
    <div className="mt-2 rounded border-l-2 border-ledger-900 bg-slate-50 px-2 py-1.5 text-sm">
      <p className="text-xs font-medium text-ledger-900">
        Response from {r.responder_name}
        {r.responder_role && <span className="font-normal text-slate-600">, {r.responder_role}</span>},{" "}
        {formatDate(r.received_at)}
      </p>
      <p className="mt-0.5 whitespace-pre-line text-slate-700">{r.text}</p>
      {r.full_text_url && (
        <a href={r.full_text_url} target="_blank" rel="noreferrer" className="text-xs text-sunshine-700 underline">
          Full response ↗
        </a>
      )}
      <p className="mt-0.5 text-[11px] text-slate-500">
        Shown as received; a response is not evidence and changes no finding. Identity {r.verified_via}.
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
            Disputed — under review
          </a>
          <span className="ml-1.5 text-slate-600">
            since {formatDate(d.disputed_since)}: challenged as {CATEGORY_NAMES[d.category] ?? d.category}. It stays
            up while it&apos;s reviewed.
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

const TRIGGER_TEXT: Record<CorrectionOut["trigger"], string> = {
  challenge: "Prompted by a reader's challenge",
  internal_review: "Found in Sunshine Ledger's own review",
  source_change: "The source changed its record",
  methodology_change: "Methodology change",
};

const OBJECT_TEXT: Record<string, string> = {
  bill: "this record",
  page_copy: "text on this page",
  claim: "a claim on this page",
  amendment: "an amendment entry",
  vote: "a roll-call vote",
};

function describeTarget(bill: BillDetail, objectType: string, objectId: string | null): string {
  if (objectType === "bill_layer" && objectId) {
    for (const [layer, blocks] of Object.entries(bill.layers)) {
      for (const b of blocks ?? []) {
        const versions = [b.current, ...b.earlier_versions];
        if (versions.some((v) => v?.id === objectId)) {
          const title = LAYER_META[layer as keyof typeof LAYER_META]?.title ?? "Who it affects";
          return `the ${title} block`;
        }
      }
    }
    return "an analysis block";
  }
  return OBJECT_TEXT[objectType] ?? "this record";
}

function originText(c: CorrectionOut): string | null {
  if (c.origin === "sunshine_ledger_ai") {
    return c.was_reviewed ? "AI-generated, reviewed by a person" : "AI-generated, not reviewed by a person";
  }
  if (c.origin === "legislative_staff") return "From the legislative staff analysis";
  if (c.origin === "bill_text") return "Quoted from the bill text";
  return null;
}

function CorrectionEntry({ bill, c }: { bill: BillDetail; c: CorrectionOut }) {
  const origin = originText(c);
  return (
    <li id={`correction-${c.id}`} className="scroll-mt-4 rounded-md border border-slate-200 p-2">
      <p className="text-sm">
        <span className="font-medium text-ledger-900">{changeLabel(c)}</span>
        <span className="text-slate-600">
          {" "}
          · {CHANGE_TYPE_NAMES[c.change_type]} ({c.severity}) to {describeTarget(bill, c.object_type, c.object_id)}
        </span>
      </p>
      <p className="mt-1 text-sm text-slate-700">{c.explanation}</p>
      {(c.prior_text || c.current_text) && (
        <details className="mt-1 text-xs text-slate-600" open={c.severity !== "minor"}>
          <summary className="cursor-pointer underline">Before and after</summary>
          {c.prior_text && (
            <div className="mt-1">
              <p className="font-medium">Earlier version{c.prior_version ? ` (version ${c.prior_version})` : ""}</p>
              <del className="block whitespace-pre-line bg-red-50 px-1 text-slate-700">{c.prior_text}</del>
            </div>
          )}
          {c.current_text && (
            <div className="mt-1">
              <p className="font-medium">
                {c.change_type === "retraction" ? "Now says" : "Corrected version"}
                {c.current_version ? ` (version ${c.current_version})` : ""}
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
              {e.role ? `${e.role[0].toUpperCase()}${e.role.slice(1)} evidence: ` : "Evidence: "}
              <a href={e.url} target="_blank" rel="noreferrer" className="text-sunshine-700 underline">
                {e.note || e.url}
              </a>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-1 text-[11px] text-slate-500">
        {TRIGGER_TEXT[c.trigger]}
        {origin && <> · {origin}</>} · decided by {c.decided_by_label}
        {c.methodology_version && <> · method {c.methodology_version}</>}
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
        Corrections, disputes and responses
      </h2>
      <p className="text-xs text-slate-500">
        Every change Sunshine Ledger makes to this page stays listed here with the earlier version and the reason.{" "}
        <Link href="/methodology#corrections" className="underline hover:text-slate-700">How corrections work</Link>
      </p>
      {disputes.length > 0 && (
        <>
          <h3 className="mt-3 text-xs font-semibold text-slate-700">Under review</h3>
          <ul className="mt-1 space-y-1 text-sm text-slate-700">
            {disputes.map((d) => (
              <li key={d.flag_id}>
                <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-900">
                  Disputed — under review
                </span>{" "}
                {describeTarget(bill, d.object_type, d.object_id)}, challenged as{" "}
                {CATEGORY_NAMES[d.category] ?? d.category}, since {formatDate(d.disputed_since)}. The statement stays
                up, labelled, until a decision is published.
              </li>
            ))}
          </ul>
        </>
      )}
      {corrections.length > 0 && (
        <>
          <h3 className="mt-3 text-xs font-semibold text-slate-700">Corrections and updates</h3>
          <ul className="mt-1 space-y-2">
            {corrections.map((c) => (
              <CorrectionEntry key={c.id} bill={bill} c={c} />
            ))}
          </ul>
        </>
      )}
      {billLevel.responses.filter((r) => !r.superseded_by_id).length > 0 && (
        <>
          <h3 className="mt-3 text-xs font-semibold text-slate-700">Responses</h3>
          {billLevel.responses.filter((r) => !r.superseded_by_id).map((r) => (
            <ResponseBlock key={r.id} r={r} />
          ))}
        </>
      )}
      {superseded.length > 0 && (
        <details className="mt-2 text-xs text-slate-500">
          <summary className="cursor-pointer underline">
            {superseded.length} earlier response{superseded.length === 1 ? "" : "s"}, since replaced by the
            responder
          </summary>
          {superseded.map((r) => (
            <ResponseBlock key={r.id} r={r} />
          ))}
        </details>
      )}
      <p className="mt-2 text-xs">
        <Link href="/corrections" className="text-sunshine-700 underline">All corrections across the site</Link>
      </p>
    </section>
  );
}
