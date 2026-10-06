/**
 * Impact Lens matcher: tests a reader's answers against a bill's Who-it-affects
 * entries and their structured criteria. Pure and synchronous. Nothing here
 * touches the network or storage, so a reader's answers never leave the browser.
 *
 * Spec: Notion "Impact Lens Structured Criteria" (the dated decisions win).
 * Criteria come from backend app/impact_lens (validate_criteria output).
 *
 * Rules, in short:
 *  - Unknown is not "no". An unanswered question, an unmapped condition or an
 *    unmapped audience makes an entry unknown, never a quiet miss.
 *  - A failing known condition or a holding exception rules an entry out.
 *  - "Does Not Appear to Apply" needs a complete Who layer; otherwise the
 *    answer is "Can't Determine".
 *  - "Anyone" entries never give the headline result; they are a separate line.
 *  - Interests are not an input: they cannot make a law apply.
 */

export type Role = string;

export interface RoleTest {
  kind: "attr";
  attr: "role";
  any_of: Role[];
}

export interface CriterionTest {
  attr: string;
  op: "in" | "not_in" | "gte" | "lte" | "between";
  values: (string | number)[];
  from: { kind: "condition" | "exception"; index: number };
}

export interface Criteria {
  entry_index: number;
  vocabulary_version: number;
  relevance: "direct" | "indirect";
  /** Who the provision binds. null = not mapped; {kind: "anyone"} = everyone. */
  audience: RoleTest | { kind: "anyone" } | null;
  /** Roles the provision protects or burdens, besides the bound party. */
  affected?: RoleTest | null;
  requires: CriterionTest[];
  excludes: CriterionTest[];
  unmapped: { kind: string; index: number | null; reason: string }[];
  ambiguous: { question: string; quote: string } | null;
  notes?: string[];
}

export interface LensEntry {
  group: string;
  /** The entry's plain-language description (stored as `text`). */
  text: string;
  quote: string;
  conditions: { text: string; quote: string }[];
  exceptions: { text: string; quote: string }[];
  /** null when the entry has not been mapped. */
  criteria: Criteria | null;
  /** true once a person has approved this mapping. */
  reviewed?: boolean;
}

export interface LensBill {
  entries: LensEntry[];
  /**
   * Server-computed: the Who layer is current and supported, did not hit its
   * entry cap, and every entry has criteria. Only then may the lens say
   * "Does Not Appear to Apply".
   */
  complete: boolean;
}

/** What a reader has chosen to tell us. Interests are deliberately absent. */
export interface Answers {
  role?: Role;
  /** County name as in the vocabulary, e.g. "Duval". */
  county?: string;
  /** Municipality name, e.g. "Jacksonville". Optional, asked after county. */
  municipality?: string;
  property_type?: string;
}

export type QuestionKey = "role" | "county" | "municipality" | "property_type";

export type ResultKind = "applies" | "may_affect" | "ambiguous" | "cant_determine" | "does_not_appear" | "everyone_only";

export const RESULT_LABEL: Record<ResultKind, string> = {
  applies: "Applies to You",
  may_affect: "May Affect You",
  ambiguous: "Text Is Ambiguous Here",
  cant_determine: "Can't Determine",
  does_not_appear: "Does Not Appear to Apply",
  // Only when every entry the bill has is an "Anyone" entry that holds: there is no
  // person-specific result to show, so the headline says what the bill does.
  everyone_only: "Applies to Everyone",
};

type Tri = "true" | "false" | "unknown";

export type EntryStatus = "match" | "no" | "unknown" | "ambiguous";
export type Relation = "bound" | "affected" | "everyone" | "none" | "unknown";

export interface EntryEvaluation {
  index: number;
  entry: LensEntry;
  status: EntryStatus;
  relation: Relation;
  /** One plain sentence saying why, for the "why" chain. */
  reason: string;
  /** Attributes still needed to settle this entry. */
  missing: QuestionKey[];
}

export interface WhyStep {
  circumstances: string[];
  quote: string;
  reasoning: string;
}

export interface LensResult {
  result: ResultKind;
  label: string;
  /** The entries that produced the headline (empty for "no" / unknown). */
  basis: EntryEvaluation[];
  /** Entries whose group is literally Anyone and that hold for this reader. */
  everyone: EntryEvaluation[];
  why: WhyStep[];
  /** What to ask next, role first. Empty once the result is settled. */
  ask: QuestionKey[];
  /** true when any entry behind the headline has not been reviewed by a person. */
  unreviewed: boolean;
  /** The ambiguity to show for the "ambiguous" result. */
  ambiguity: { question: string; quote: string } | null;
  evaluations: EntryEvaluation[];
}

// ---- three-valued tests ---------------------------------------------------

const tri = (b: boolean): Tri => (b ? "true" : "false");
const negate = (t: Tri): Tri => (t === "true" ? "false" : t === "false" ? "true" : "unknown");

function roleIn(test: RoleTest, answers: Answers): Tri {
  if (answers.role === undefined) return "unknown";
  return tri(test.any_of.includes(answers.role));
}

function jurisdictionIn(values: (string | number)[], answers: Answers): Tri {
  let sawUnknown = false;
  for (const raw of values) {
    const [kind, ...rest] = String(raw).split(":");
    const name = rest.join(":");
    if (kind === "county") {
      if (answers.county === undefined) sawUnknown = true;
      else if (answers.county === name) return "true";
    } else if (kind === "municipality") {
      if (answers.municipality === undefined) sawUnknown = true;
      else if (answers.municipality === name) return "true";
    }
  }
  return sawUnknown ? "unknown" : "false";
}

function testCriterion(t: CriterionTest, answers: Answers): { r: Tri; missing: QuestionKey[] } {
  if (t.attr === "jurisdiction") {
    const base = t.op === "in" || t.op === "not_in" ? jurisdictionIn(t.values, answers) : "unknown";
    const r = t.op === "not_in" ? negate(base) : base;
    const missing: QuestionKey[] = [];
    if (r === "unknown") {
      if (answers.county === undefined) missing.push("county");
      else if (t.values.some((v) => String(v).startsWith("municipality:"))) missing.push("municipality");
    }
    return { r, missing };
  }
  if (t.attr === "property_type") {
    const a = answers.property_type;
    if (a === undefined) return { r: "unknown", missing: ["property_type"] };
    const inSet = t.values.includes(a);
    return { r: tri(t.op === "not_in" ? !inSet : inSet), missing: [] };
  }
  // An attribute this version of the matcher does not know cannot be tested.
  return { r: "unknown", missing: [] };
}

// ---- one entry ------------------------------------------------------------

function relationOf(c: Criteria, answers: Answers): { relation: Relation; missing: QuestionKey[] } {
  if (c.audience && c.audience.kind === "anyone") return { relation: "everyone", missing: [] };

  const bound: Tri = c.audience && c.audience.kind === "attr" ? roleIn(c.audience, answers) : "unknown";
  const affected: Tri = c.affected ? roleIn(c.affected, answers) : "false";

  if (bound === "true") return { relation: "bound", missing: [] };
  if (affected === "true") return { relation: "affected", missing: [] };
  if (bound === "false" && affected === "false") return { relation: "none", missing: [] };
  // Not enough to say. If the reader has given a role, the gap is in the
  // criteria (an unmapped audience), not something a question could settle.
  return { relation: "unknown", missing: answers.role === undefined ? ["role"] : [] };
}

export function evaluateEntry(entry: LensEntry, index: number, answers: Answers): EntryEvaluation {
  const make = (status: EntryStatus, relation: Relation, reason: string, missing: QuestionKey[] = []): EntryEvaluation => ({
    index,
    entry,
    status,
    relation,
    reason,
    missing,
  });

  const c = entry.criteria;
  if (!c) return make("unknown", "unknown", "This provision has not been mapped to questions yet.");

  const { relation, missing: roleMissing } = relationOf(c, answers);
  if (relation === "none") {
    return make("no", "none", `Your answer for role is outside who this provision is about (${entry.group}).`);
  }

  // A known failing requirement or a holding exception rules the entry out,
  // whatever else is unknown or unmapped.
  const missing: QuestionKey[] = [...roleMissing];
  let unknown = relation === "unknown";
  for (const t of c.requires) {
    const { r, missing: m } = testCriterion(t, answers);
    if (r === "false") {
      return make("no", relation, `A condition the bill states is not met by your answers: ${entry.conditions[t.from.index]?.text ?? "a condition"}.`);
    }
    if (r === "unknown") {
      unknown = true;
      missing.push(...m);
    }
  }
  for (const t of c.excludes) {
    const { r, missing: m } = testCriterion(t, answers);
    if (r === "true") {
      return make("no", relation, `An exception the bill states applies to you: ${entry.exceptions[t.from.index]?.text ?? "an exception"}.`);
    }
    if (r === "unknown") {
      unknown = true;
      missing.push(...m);
    }
  }
  // Conditions and exceptions we could not turn into a question stay unknown.
  if (c.unmapped.some((u) => u.kind !== "audience")) unknown = true;

  const uniqueMissing = [...new Set(missing)];
  if (c.ambiguous) {
    return make("ambiguous", relation, `The text is ambiguous here: ${c.ambiguous.question}`, uniqueMissing);
  }
  if (unknown) {
    return make("unknown", relation, relation === "unknown" ? "We cannot tell whether this provision is about you." : "Part of this provision's conditions cannot be tested from the answers we ask for.", uniqueMissing);
  }
  const why =
    relation === "everyone"
      ? "This provision applies to everyone."
      : relation === "affected"
        ? "This provision protects or burdens people like you."
        : "This provision is about you, and every condition the bill states holds for your answers.";
  return make("match", relation, why);
}

// ---- the bill -------------------------------------------------------------

function circumstances(answers: Answers): string[] {
  const out: string[] = [];
  if (answers.role !== undefined) out.push(`Role: ${answers.role}`);
  if (answers.county !== undefined) out.push(`County: ${answers.county}`);
  if (answers.municipality !== undefined) out.push(`Municipality: ${answers.municipality}`);
  if (answers.property_type !== undefined) out.push(`Property type: ${answers.property_type}`);
  return out;
}

const ASK_ORDER: QuestionKey[] = ["role", "county", "municipality", "property_type"];

export function matchBill(bill: LensBill, answers: Answers): LensResult {
  const evaluations = bill.entries.map((e, i) => evaluateEntry(e, i, answers));

  const personal = evaluations.filter((e) => e.relation !== "everyone");
  const everyone = evaluations.filter((e) => e.relation === "everyone" && e.status === "match");

  const matches = personal.filter((e) => e.status === "match");
  const direct = matches.filter((e) => (e.entry.criteria?.relevance ?? "direct") === "direct");
  const indirect = matches.filter((e) => e.entry.criteria?.relevance === "indirect");
  // Uncertainty counts from every entry, "Anyone" ones included: an Anyone entry
  // with an untestable condition may still apply to this reader.
  const ambiguous = evaluations.filter((e) => e.status === "ambiguous");
  const unknown = evaluations.filter((e) => e.status === "unknown");

  let result: ResultKind;
  let basis: EntryEvaluation[] = [];
  if (direct.length) {
    result = "applies";
    basis = direct;
  } else if (indirect.length) {
    result = "may_affect";
    basis = indirect;
  } else if (ambiguous.length) {
    result = "ambiguous";
    basis = ambiguous;
  } else if (unknown.length || bill.entries.length === 0) {
    result = "cant_determine";
    basis = unknown;
  } else if (personal.length === 0 && everyone.length > 0) {
    result = "everyone_only";
  } else if (bill.complete) {
    result = "does_not_appear";
  } else {
    // Every entry we have rules the reader out, but the list may be incomplete.
    result = "cant_determine";
  }

  const settled = result === "applies" || result === "may_affect";
  const askSet = new Set<QuestionKey>();
  if (!settled) {
    for (const e of [...unknown, ...ambiguous]) e.missing.forEach((m) => askSet.add(m));
  }
  const ask = ASK_ORDER.filter((q) => askSet.has(q));

  const why: WhyStep[] = basis
    .filter((e) => result === "applies" || result === "may_affect" || result === "ambiguous")
    .map((e) => ({ circumstances: circumstances(answers), quote: e.entry.quote, reasoning: e.reason }));

  const ambiguity = result === "ambiguous" ? (basis[0]?.entry.criteria?.ambiguous ?? null) : null;
  const unreviewed = basis.some((e) => e.entry.reviewed !== true);

  return { result, label: RESULT_LABEL[result], basis, everyone, why, ask, unreviewed, ambiguity, evaluations };
}

// ---- the API response (GET /bills/{id}/impact-lens) -----------------------

export interface LensOption {
  value: string;
  label: string;
}

export interface LensQuestion {
  /** The matcher's answer key. */
  key: QuestionKey;
  label: string;
  question: string;
  /** Every list ends with a "none_of_these" option. */
  options: LensOption[];
  /** municipality only: the counties each option lies in. */
  counties?: Record<string, string[]> | null;
}

export interface ImpactLensResponse {
  bill_entity_id: string;
  available: boolean;
  unavailable_reason: string | null;
  vocabulary_version: number;
  complete: boolean;
  incomplete_reasons: string[];
  layer: { id: string; version: number; evidence_state: string; scope_note: string; method_version: string; created_at: string } | null;
  entries: LensEntry[];
  questions: LensQuestion[];
}

export function toLensBill(r: ImpactLensResponse): LensBill {
  return { entries: r.entries, complete: r.complete };
}

/** Answers are only ever these four keys; anything else in storage is dropped. */
export const ANSWER_KEYS: QuestionKey[] = ["role", "county", "municipality", "property_type"];

export function cleanAnswers(raw: unknown): Answers {
  const out: Answers = {};
  if (raw && typeof raw === "object") {
    for (const k of ANSWER_KEYS) {
      const v = (raw as Record<string, unknown>)[k];
      if (typeof v === "string" && v) out[k] = v;
    }
  }
  return out;
}
