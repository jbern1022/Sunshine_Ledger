/** Privacy-safe usage counts (docs/USAGE_COUNTS_DESIGN.md).
 *
 *  Daily totals of three events by page kind. Nothing identifying is sent:
 *  no bill, person or district id, no URL, no search text, no cookie or
 *  storage. Off unless NEXT_PUBLIC_USAGE_COUNTS_ENABLED is "true", because
 *  switching it on changes a promise on /privacy. */

export const USAGE_COUNTS_ENABLED = process.env.NEXT_PUBLIC_USAGE_COUNTS_ENABLED === "true";
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type UsageEvent = "page_view" | "bill_read" | "source_click";
export type PageKind =
  | "home" | "browse" | "bill" | "person" | "district" | "map"
  | "promises" | "corrections" | "methodology" | "other";

/** How long a bill page must stay visible before it counts as read. */
export const BILL_READ_MS = 15_000;

const KIND_BY_SEGMENT: Record<string, PageKind> = {
  bills: "bill",
  people: "person",
  districts: "district",
  map: "map",
  promises: "promises",
  corrections: "corrections",
  methodology: "methodology",
};

/** The page's kind from its path. Never returns the path itself. */
export function pageKindFor(pathname: string): PageKind {
  const segments = pathname.split("/").filter(Boolean);
  if (segments.length === 0) return "home";
  const kind = KIND_BY_SEGMENT[segments[0]];
  if (!kind) return "other";
  // /bills and /people without an id are lists, i.e. browsing.
  if ((kind === "bill" || kind === "person") && segments.length === 1) return "browse";
  return kind;
}

// Official record hosts a reader can verify against. Suffix match.
const OFFICIAL_HOSTS = [
  "flsenate.gov", "myfloridahouse.gov", "leg.state.fl.us", "dos.fl.gov", "legiscan.com",
  "legistar.com", "granicus.com", "iqm2.com", "escribemeetings.com",
  "congress.gov", "house.gov", "senate.gov", "govinfo.gov", "census.gov", "bls.gov",
];

export function isOfficialSource(href: string): boolean {
  let host: string;
  try {
    host = new URL(href).hostname.toLowerCase();
  } catch {
    return false;
  }
  return OFFICIAL_HOSTS.some((h) => host === h || host.endsWith(`.${h}`));
}

/** Send one event, or nothing at all when switched off, automated or hidden. */
export function sendUsage(event: UsageEvent, pageKind: PageKind): void {
  if (!USAGE_COUNTS_ENABLED || typeof window === "undefined") return;
  if (navigator.webdriver || document.visibilityState !== "visible") return;
  const body = JSON.stringify({ event, page_kind: pageKind });
  // keepalive so a source click still counts as the page navigates away. No credentials: nothing to identify.
  void fetch(`${API_URL}/usage`, {
    method: "POST",
    body,
    headers: { "Content-Type": "application/json" },
    keepalive: true,
    credentials: "omit",
  }).catch(() => {});
}
