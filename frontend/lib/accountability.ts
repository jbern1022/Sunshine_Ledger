import type { BillDetail, ChangeType, CorrectionOut, DisputeOut, ResponseOut } from "./types";
import { formatDate } from "./layers";

/** Correction-process presentation (Notion spec "Correction, Dispute &
 *  Right-of-Reply Process", step 4): which disputes, corrections and
 *  responses belong to a block or record, and how they're labelled. */

export type Accountability = Pick<BillDetail, "disputes" | "corrections" | "responses">;

export interface TargetAccountability {
  disputes: DisputeOut[];
  corrections: CorrectionOut[];
  responses: ResponseOut[];
}

const BILL_LEVEL = new Set(["bill", "page_copy"]);

/** Everything aimed at one object. A layer block is matched by any of its
 *  version ids, since a challenge names the version it disputed and a
 *  correction may point at the replaced one. "bill" covers page copy too. */
export function forTarget(bill: Accountability, objectType: string, ids: string[]): TargetAccountability {
  const idSet = new Set(ids);
  const matches = (t: { object_type: string; object_id: string | null }) =>
    objectType === "bill" ? BILL_LEVEL.has(t.object_type) : t.object_type === objectType && t.object_id !== null && idSet.has(t.object_id);
  return {
    disputes: (bill.disputes ?? []).filter(matches),
    corrections: (bill.corrections ?? []).filter(matches),
    responses: (bill.responses ?? []).filter(matches),
  };
}

const VERB: Record<ChangeType, string> = {
  update: "Updated",
  correction: "Corrected",
  clarification: "Clarified",
  retraction: "Retracted",
  source_correction: "Source corrected",
};

export function changeLabel(c: CorrectionOut): string {
  return `${VERB[c.change_type]} ${formatDate(c.decided_at)}`;
}

export const CHANGE_TYPE_NAMES: Record<ChangeType, string> = {
  update: "Update",
  correction: "Correction",
  clarification: "Clarification",
  retraction: "Retraction",
  source_correction: "Source correction",
};

export const CATEGORY_NAMES: Record<string, string> = {
  factually_wrong: "factually wrong",
  misleading: "misleading or missing context",
  wrong_source: "wrong source or quote",
  outdated: "outdated",
  wrong_entity: "wrong person or organization",
  other: "other",
};

function clip(text: string, max = 240): string {
  return text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text;
}

/** The one-line note a Material or Critical change gets on the page. Minor
 *  fixes get none (they stay in the record's history). A source's own
 *  correction is never worded as a Sunshine Ledger error. */
export function correctionNote(c: CorrectionOut): string | null {
  if (c.severity === "minor") return null;
  if (c.change_type === "source_correction") return `The source corrected its own record. ${c.explanation}`;
  const verb = VERB[c.change_type];
  return c.prior_text
    ? `An earlier version said “${clip(c.prior_text)}” ${verb} because: ${c.explanation}`
    : `${verb} because: ${c.explanation}`;
}
