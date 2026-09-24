/** Inline change markers in stored bill text.
 *
 *  The backend stores `full_text` (and amendment text) with the bill's own
 *  edits kept inline: `[deleted: …]` for wording the bill strikes and
 *  `[added: …]` for wording it adds. These helpers let the UI show those
 *  edits as real <del>/<ins> instead of raw brackets, and derive the "law
 *  as amended" view (deletions dropped, additions unwrapped) -- the same
 *  view the backend's `law_as_amended` produces.
 */

export type MarkerSegment = { kind: "text" | "deleted" | "added"; text: string };

const MARKER = /\[(deleted|added): ([^\]]*)(\]|$)/g;

/** Split text into plain / deleted / added segments, in order.
 *  A marker cut off at the end of the text (no closing `]`) still counts as
 *  a marker, so a truncated fragment is never shown as plain wording. */
export function parseChangeMarkers(text: string): MarkerSegment[] {
  const segments: MarkerSegment[] = [];
  let last = 0;
  for (const match of text.matchAll(MARKER)) {
    const start = match.index ?? 0;
    if (start > last) segments.push({ kind: "text", text: text.slice(last, start) });
    segments.push({ kind: match[1] as "deleted" | "added", text: match[2] });
    last = start + match[0].length;
  }
  if (last < text.length) segments.push({ kind: "text", text: text.slice(last) });
  return segments;
}

const DELETED_BEFORE_PUNCT = / ?\[deleted:[^\]]*\](?=[,.;:)])/g;
const DELETED = /\[deleted:[^\]]*\]/g;
const ADDED = /\[added:\s*([^\]]*)\]/g;
const DELETED_UNTERMINATED = /\s?\[deleted:[^\]]*$/;
const ADDED_UNTERMINATED = /\[added:\s*([^\]]*)$/;
const DOUBLE_SPACE = /[ \t]{2,}/g;

/** The text as the law will read once the bill takes effect: `[deleted: …]`
 *  dropped, `[added: …]` unwrapped. Mirrors the backend's `law_as_amended`,
 *  including collapsing the extra space a removed marker leaves behind. */
export function lawAsAmended(text: string): string {
  return text
    .replace(DELETED_BEFORE_PUNCT, "")
    .replace(DELETED, "")
    .replace(ADDED, "$1")
    .replace(DELETED_UNTERMINATED, "")
    .replace(ADDED_UNTERMINATED, "$1")
    .replace(DOUBLE_SPACE, " ");
}
