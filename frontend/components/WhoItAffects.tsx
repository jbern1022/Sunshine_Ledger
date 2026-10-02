import type { LayerBlock, LayerItem } from "@/lib/types";
import { billTextLabel, formatDate, reviewLabel } from "@/lib/layers";
import { applicability } from "@/lib/billStatus";
import { FlagThis } from "@/components/ChallengeForm";
import { AccountabilityNotes } from "@/components/Accountability";
import { forTarget, type Accountability } from "@/lib/accountability";

/** The bill's sentence, preceded by the plain-language restatement only
 *  when that says something different (models often copy the sentence). */
function clause(text: string, quote: string) {
  const same = text.replace(/\W+/g, " ").trim().toLowerCase() === quote.replace(/\W+/g, " ").trim().toLowerCase();
  return same ? <q className="italic">{quote}</q> : <>{text} — <q className="italic">{quote}</q></>;
}

/** Who the bill directly applies to, group by group: what changes, the
 *  provision that changes it, and the conditions and exceptions the bill
 *  states. Rules: Data Model v1, "Scope and Affected Population".
 *
 *  The verb ("Would apply to" ... "Applies to") comes from the bill's status
 *  now, not from when the block was generated, so it can't go stale. A group
 *  may appear more than once (different roles); there is deliberately no
 *  overall verdict. Server-rendered, no interactivity. */

type Props = {
  billEntityId: string;
  block: LayerBlock;
  status: string | null | undefined;
  effective: { when: string; has_exceptions: boolean } | null | undefined;
  accountability?: Accountability;
};

const KIND_LABEL: Record<string, string> = {
  obligation: "Obligation",
  permission: "Permission",
  eligibility: "Eligibility",
  protection: "Protection",
  cost: "Cost",
  service: "Service",
  prohibition: "Prohibition",
  other: "Other change",
};

// The rest of a long list folds behind "Show N more" (R9): nothing is cut.
const SHOWN = 6;

export default function WhoItAffects({ billEntityId, block, status, effective, accountability }: Props) {
  const version = block.current;
  const { verb, note } = applicability(status, effective);
  const entry = (item: LayerItem, i: number) => (
    <li key={i}>
      <p>
        <span className="text-slate-500">{verb} </span>
        <span className="font-medium text-ledger-900">{item.group}</span>: {item.text}
        {item.change_kind && (
          <span className="ml-1.5 rounded bg-slate-100 px-1.5 text-xs text-slate-600">
            {KIND_LABEL[item.change_kind] ?? KIND_LABEL.other}
          </span>
        )}
        {item.restates_existing_law && (
          <span className="ml-1.5 rounded border border-slate-200 px-1.5 text-xs text-slate-500">
            Existing law, not changed by this bill
          </span>
        )}
      </p>
      {item.quote && (
        <p className="mt-0.5 text-xs text-slate-500">
          Why: <q className="italic">{item.quote}</q>
          {(item.section_ref || item.statute_ref) && <> ({[item.section_ref, item.statute_ref].filter(Boolean).join(", ")})</>}
        </p>
      )}
      {(item.also_in ?? []).map((a, j) => (
        <p key={`a${j}`} className="mt-0.5 text-xs text-slate-500">
          Same rule: <q className="italic">{a.quote}</q>
          {(a.section_ref || a.statute_ref) && <> ({[a.section_ref, a.statute_ref].filter(Boolean).join(", ")})</>}
        </p>
      ))}
      {(item.conditions ?? []).map((c, j) => (
        <p key={`c${j}`} className="mt-0.5 text-xs text-slate-500">
          Condition: {clause(c.text, c.quote)}
        </p>
      ))}
      {(item.exceptions ?? []).map((x, j) => (
        <p key={`x${j}`} className="mt-0.5 text-xs text-slate-500">
          Exception stated in the bill: {clause(x.text, x.quote)}
        </p>
      ))}
    </li>
  );

  return (
    <section aria-labelledby="who-it-affects" className="mt-5">
      <h2 id="who-it-affects" className="text-sm font-semibold text-ledger-900">Who it affects</h2>
      <p className="text-xs text-slate-500">
        Who the bill directly applies to and what changes for them. Possible knock-on effects are under Expected Effect.
      </p>
      <div className="mt-3 rounded border border-slate-200 p-3">
        <h3 className="text-xs font-medium">
          <span className="rounded bg-sunshine-100 px-1.5 py-0.5 text-sunshine-800">Sunshine Ledger analysis · AI-generated</span>
          {reviewLabel("sunshine_ledger_ai", version) && (
            <span className={`ml-1.5 ${version.review_status === "reviewed" ? "text-ledger-900" : "text-slate-500"}`}>
              · {reviewLabel("sunshine_ledger_ai", version)}
            </span>
          )}
        </h3>
        {accountability && (
          <AccountabilityNotes
            items={forTarget(accountability, "bill_layer", [version.id, ...block.earlier_versions.map((v) => v.id)])}
          />
        )}
        {version.evidence_state === "insufficient_evidence" ? (
          <p className="mt-1 text-sm text-slate-600">
            <span className="font-medium">Insufficient evidence</span> — {version.scope_note}
          </p>
        ) : (
          <>
            {note && <p className="mt-1 text-xs text-slate-500">{note === "if enacted" ? "Only if the bill is enacted." : note}</p>}
            <ul className="mt-1 space-y-3 text-sm leading-relaxed text-slate-700">
              {version.items.slice(0, SHOWN).map((item, i) => entry(item, i))}
            </ul>
            {version.items.length > SHOWN && (
              <details className="mt-3">
                <summary className="cursor-pointer text-xs text-slate-600 underline">
                  Show {version.items.length - SHOWN} more
                </summary>
                <ul className="mt-2 space-y-3 text-sm leading-relaxed text-slate-700">
                  {version.items.slice(SHOWN).map((item, i) => entry(item, SHOWN + i))}
                </ul>
              </details>
            )}
            <p className="mt-2 text-[11px] text-slate-500">
              Each reason is checked word for word against the bill text. Conditions and exceptions are listed only
              where the bill states them; its definitions may narrow who is covered. Belonging to a group doesn&apos;t
              mean every condition applies to you.
            </p>
            {version.scope_note !== "Bill text" && (
              <p className="mt-1 text-[11px] text-slate-500">
                {version.scope_note.startsWith("Sections ") ? `Drawn from ${version.scope_note}` : version.scope_note}
              </p>
            )}
          </>
        )}
        {version.sources.length > 0 && (
          <p className="mt-2 text-[11px] text-slate-500">
            Source:{" "}
            {version.sources.map((s, i) => (
              <span key={s.id}>
                {i > 0 && "; "}
                {s.url ? (
                  <a href={s.url} className="underline hover:text-slate-700">
                    {billTextLabel(s)}
                  </a>
                ) : (
                  billTextLabel(s)
                )}
              </span>
            ))}
          </p>
        )}
        <p className="mt-1 text-[11px] text-slate-500">
          {version.generated_by.replace(/^llm:/, "Model: ")} · method {version.method_version} · updated{" "}
          {formatDate(version.created_at)}
          {block.earlier_versions.length > 0 &&
            ` · ${block.earlier_versions.length} earlier version${block.earlier_versions.length === 1 ? "" : "s"} kept`}
        </p>
        <FlagThis
          billEntityId={billEntityId}
          target={{ object_type: "bill_layer", object_id: version.id, object_version: version.version }}
          label="Flag this block"
        />
      </div>
    </section>
  );
}
