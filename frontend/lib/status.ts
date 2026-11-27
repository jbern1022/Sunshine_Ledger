/** The public status page published from AWS (infra/aws/status), read on the
 *  server so a reader's browser never contacts a third party (see /privacy). */

export const STATUS_PAGE_URL = process.env.STATUS_PAGE_URL || "https://d21z9fmiu2i8g3.cloudfront.net/";

export type UptimeWindow = { uptime_pct: number | null; coverage_pct: number; down_periods: number };
export type Incident = { start: string; end: string | null; minutes: number; note: string | null };
export type PublishedStatus = {
  generated_at: string;
  current: "up" | "down" | "unknown";
  measured_since: string | null;
  method: string;
  windows: Record<string, UptimeWindow>;
  incidents: Incident[];
  data: { reachable: boolean; last_ingest_at?: string | null; sources_total?: number; sources_fresh?: number };
};

export async function getPublishedStatus(): Promise<PublishedStatus | null> {
  try {
    const res = await fetch(new URL("status.json", STATUS_PAGE_URL), { next: { revalidate: 60 } });
    if (!res.ok) return null;
    return (await res.json()) as PublishedStatus;
  } catch {
    return null;
  }
}
