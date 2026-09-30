import { diffArrays, diffWordsWithSpace, type Change } from "diff";
import { lawAsAmended } from "./changeMarkers";

/** Comparing a bill's filed text with its current text.
 *
 *  Stored texts keep the PDF's line breaks, and a re-filed version wraps
 *  differently, so comparing lines would flag nearly every line. Both texts
 *  are compared as the law would read (the bill's own [deleted:]/[added:]
 *  markers resolved, as AmendmentDiff does), with whitespace collapsed and
 *  split into clauses at sentence and semicolon boundaries. Clauses are
 *  diffed first; words only inside changed stretches, which keeps a
 *  120k-character bill responsive.
 */

/** Longer texts get links to the official versions instead of a comparison. */
export const MAX_COMPARE_CHARS = 200_000;
/** Below this similarity a version was rewritten, not edited. */
export const REWRITTEN_BELOW = 0.3;
/** A changed stretch longer than this is shown as removed/added blocks
 *  without a word-level diff (the diff gets slow and unreadable). */
const MAX_WORD_DIFF_CHARS = 20_000;

export type CompareBlock =
  | { kind: "same"; clauses: string[] }
  | { kind: "changed"; parts: Change[] };

export interface Comparison {
  /** 0..1: share of the two texts' characters left unchanged (whole
   *  clauses, plus unchanged words inside changed stretches). */
  similarity: number;
  rewritten: boolean;
  blocks: CompareBlock[];
}

export function splitClauses(text: string): string[] {
  const flat = lawAsAmended(text).replace(/\s+/g, " ").trim();
  if (!flat) return [];
  return flat.split(/(?<=[.;:])\s+(?=[A-Z0-9(“"])/);
}

function changedParts(removed: string[], added: string[]): Change[] {
  const before = removed.join(" ");
  const after = added.join(" ");
  if (before.length + after.length > MAX_WORD_DIFF_CHARS || !before || !after) {
    return [
      ...(before ? [{ value: before, removed: true, added: false, count: removed.length }] : []),
      ...(after ? [{ value: after, added: true, removed: false, count: added.length }] : []),
    ] as Change[];
  }
  return diffWordsWithSpace(before, after);
}

export function compareTexts(filed: string, current: string): Comparison {
  const a = splitClauses(filed);
  const b = splitClauses(current);
  const total = a.join(" ").length + b.join(" ").length;
  const blocks: CompareBlock[] = [];
  let removed: string[] = [];
  let added: string[] = [];
  let sameChars = 0;

  const flush = () => {
    if (removed.length || added.length) {
      const parts = changedParts(removed, added);
      for (const p of parts) if (!p.added && !p.removed) sameChars += 2 * p.value.length;
      blocks.push({ kind: "changed", parts });
    }
    removed = [];
    added = [];
  };

  for (const chunk of diffArrays(a, b)) {
    if (chunk.removed) removed.push(...chunk.value);
    else if (chunk.added) added.push(...chunk.value);
    else {
      flush();
      blocks.push({ kind: "same", clauses: chunk.value });
      sameChars += 2 * chunk.value.join(" ").length;
    }
  }
  flush();

  const similarity = total ? Math.min(1, sameChars / total) : 1;
  return { similarity, rewritten: similarity < REWRITTEN_BELOW, blocks };
}
