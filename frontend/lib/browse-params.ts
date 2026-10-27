/** Browse-page filters that live in the URL, so a filtered view can be
 *  shared and the back/forward buttons walk through it. Params this module
 *  doesn't own (geo, sponsor, sponsorName, auto) pass through untouched. */
export const BROWSE_PAGE_SIZE = 50;

export interface BrowseFilters {
  q: string;
  jurisdiction: string;
  status: string;
  session: string;
  tag: string;
  /** 1-based. */
  page: number;
}

const FILTER_KEYS = ["q", "jurisdiction", "status", "session", "tag"] as const;

export function parseBrowseParams(params: URLSearchParams): BrowseFilters {
  const page = Number.parseInt(params.get("page") ?? "", 10);
  return {
    q: params.get("q") ?? "",
    jurisdiction: params.get("jurisdiction") ?? "",
    status: params.get("status") ?? "",
    session: params.get("session") ?? "",
    tag: params.get("tag") ?? "",
    page: Number.isFinite(page) && page > 1 ? page : 1,
  };
}

/** The query string after applying `patch` to `current`. Changing any filter
 *  returns to page 1 unless the patch sets the page itself; empty values and
 *  page 1 are left out so the default view keeps a clean URL. */
export function buildBrowseQuery(current: URLSearchParams, patch: Partial<BrowseFilters>): string {
  const next = new URLSearchParams(current);
  const changesFilter = FILTER_KEYS.some((k) => k in patch);
  for (const key of FILTER_KEYS) {
    if (!(key in patch)) continue;
    const value = patch[key];
    if (value) next.set(key, value);
    else next.delete(key);
  }
  if (patch.page !== undefined) {
    if (patch.page > 1) next.set("page", String(patch.page));
    else next.delete("page");
  } else if (changesFilter) {
    next.delete("page");
  }
  // A manual jurisdiction choice ends the "based on your location" note.
  if ("jurisdiction" in patch) next.delete("auto");
  return next.toString();
}
