import type { EarmarkList, BillDetail, BillListResponse, CorrectionLogEntry, PersonDetail, PersonListResponse, SourceStatus,
  PromiseList,
  DistrictList,
  DistrictDetail,
  FloridaPlaces,
} from "./types";

/** Server-side API base.
 *
 *  NEXT_PUBLIC_API_URL is the public hostname, which works from a browser
 *  but makes a server-side fetch leave the host and come back in through
 *  the tunnel. INTERNAL_API_URL lets the container talk to the API directly
 *  over the compose network instead; it falls back to the public URL so
 *  local runs and builds still work.
 */
const SERVER_API_URL =
  process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Fetch a bill on the server. Returns null for anything non-200 so a page
 *  can render a proper not-found rather than throwing during render. */
export async function getBill(entityId: string): Promise<BillDetail | null> {
  try {
    const res = await fetch(`${SERVER_API_URL}/bills/${entityId}`, {
      // Bill status changes as legislation moves; an hour keeps pages fresh
      // without hitting the API on every crawl.
      next: { revalidate: 3600 },
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

/** Every bill id, for the sitemap. Paged because the corpus is ~2,400 and
 *  the API caps `limit` at 100. */
export async function getAllBillsForSitemap(): Promise<
  Array<{ entity_id: string; last_action_date: string | null }>
> {
  const out: Array<{ entity_id: string; last_action_date: string | null }> = [];
  const pageSize = 100;

  for (let offset = 0; ; offset += pageSize) {
    let page: BillListResponse;
    try {
      const res = await fetch(`${SERVER_API_URL}/bills?limit=${pageSize}&offset=${offset}`, {
        next: { revalidate: 3600 },
      });
      if (!res.ok) break;
      page = await res.json();
    } catch {
      break;
    }

    out.push(
      ...page.items.map((b) => ({ entity_id: b.entity_id, last_action_date: b.last_action_date })),
    );

    // Stop on a short page or once the reported total is covered, and keep a
    // hard ceiling so a pagination bug can't spin here forever.
    if (page.items.length < pageSize || out.length >= page.total || out.length >= 10000) break;
  }

  return out;
}

/** Fetch a sponsor on the server. Same rationale as getBill: "who sponsored
 *  this" is a real search query, and a client-rendered page answers it with
 *  an empty shell. */
export async function getPerson(entityId: string): Promise<PersonDetail | null> {
  try {
    const res = await fetch(`${SERVER_API_URL}/people/${entityId}`, {
      next: { revalidate: 3600 },
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

/** Sponsor ids for the sitemap. */
export async function getAllPeopleForSitemap(): Promise<string[]> {
  try {
    const res = await fetch(`${SERVER_API_URL}/people?limit=200`, { next: { revalidate: 3600 } });
    if (!res.ok) return [];
    const page: PersonListResponse = await res.json();
    return page.items.map((p) => p.entity_id);
  } catch {
    return [];
  }
}

/** Recently-active bills for the RSS feed. The bills API already orders by
 *  last action, so "recent" needs no extra parameter. */
export async function getRecentBillsForFeed(limit = 50): Promise<BillListResponse["items"]> {
  try {
    const res = await fetch(`${SERVER_API_URL}/bills?limit=${limit}`, {
      next: { revalidate: 3600 },
    });
    if (!res.ok) return [];
    const page: BillListResponse = await res.json();
    return page.items;
  } catch {
    return [];
  }
}

/** Data source freshness for server-rendered pages. Null if the API is
 *  unreachable, so a page renders without the note rather than failing. */
export async function getSourceStatus(): Promise<SourceStatus[] | null> {
  try {
    const res = await fetch(`${SERVER_API_URL}/sources/status`, { next: { revalidate: 600 } });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

/** The public corrections log (Material and Critical; filters optional).
 *  Null when the API can't be reached, so the page can say so instead of
 *  claiming there are no corrections. */
export async function getCorrections(filters: { change_type?: string; severity?: string } = {}): Promise<
  CorrectionLogEntry[] | null
> {
  const qs = new URLSearchParams({ limit: "200" });
  if (filters.change_type) qs.set("change_type", filters.change_type);
  if (filters.severity) qs.set("severity", filters.severity);
  try {
    const res = await fetch(`${SERVER_API_URL}/corrections?${qs}`, { next: { revalidate: 600 } });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

/** Collected promise statements. Null when the API can't be reached, so the
 *  page says so instead of claiming nothing was collected. */
export async function getPromises(filters: { chamber?: string; district?: number } = {}): Promise<PromiseList | null> {
  const qs = new URLSearchParams({ limit: "100" });
  if (filters.chamber) qs.set("chamber", filters.chamber);
  if (filters.district) qs.set("district", String(filters.district));
  try {
    const res = await fetch(`${SERVER_API_URL}/promises?${qs}`, { next: { revalidate: 600 } });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function getDistricts(): Promise<DistrictList | null> {
  try {
    const res = await fetch(`${SERVER_API_URL}/districts`, { next: { revalidate: 3600 } });
    return res.ok ? res.json() : null;
  } catch {
    return null;
  }
}

/** One district. Null when the API can't be reached; undefined when it says the district does not exist. */
export async function getDistrict(code: string): Promise<DistrictDetail | null | undefined> {
  try {
    const res = await fetch(`${SERVER_API_URL}/districts/${encodeURIComponent(code)}`, { next: { revalidate: 600 } });
    if (res.status === 404) return undefined;
    return res.ok ? res.json() : null;
  } catch {
    return null;
  }
}

/** Florida places named in a federal bill's text. Null when unavailable. */
export async function getFloridaPlaces(entityId: string): Promise<FloridaPlaces | null> {
  try {
    const res = await fetch(`${SERVER_API_URL}/bills/${entityId}/florida-places`, { next: { revalidate: 600 } });
    return res.ok ? res.json() : null;
  } catch {
    return null;
  }
}

/** Community Project Funding rows for one congressional district. Null when unavailable. */
export async function getEarmarks(district: string, limit = 25): Promise<EarmarkList | null> {
  try {
    const res = await fetch(`${SERVER_API_URL}/earmarks?district=${encodeURIComponent(district)}&limit=${limit}`, { next: { revalidate: 3600 } });
    return res.ok ? res.json() : null;
  } catch {
    return null;
  }
}

/** Project-funding rows linked to one person (a Florida House member). Null when unavailable. */
export async function getPersonEarmarks(personId: string, limit = 25): Promise<EarmarkList | null> {
  try {
    const res = await fetch(`${SERVER_API_URL}/earmarks?person_id=${encodeURIComponent(personId)}&limit=${limit}`, { next: { revalidate: 3600 } });
    return res.ok ? res.json() : null;
  } catch {
    return null;
  }
}
