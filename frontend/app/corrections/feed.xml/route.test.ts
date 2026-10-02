import { describe, it, expect, vi } from "vitest";

vi.mock("@/lib/server-api", () => ({ getCorrections: vi.fn() }));

import { getCorrections } from "@/lib/server-api";
import { GET } from "./route";
import type { CorrectionLogEntry } from "@/lib/types";

const entry: CorrectionLogEntry = {
  id: "c1", bill_entity_id: "b1", object_type: "bill_layer", object_id: "l1", prior_version: 1, current_version: 2,
  prior_text: "Old", current_text: "New", change_type: "correction", severity: "material", trigger: "challenge",
  explanation: "The threshold is 40% <of units>, not 30%.", evidence_links: [], origin: "sunshine_ledger_ai",
  was_reviewed: false, methodology_version: null, decided_at: "2026-10-02T12:00:00Z",
  decided_by_label: "Sunshine Ledger editor", bill_number: "H1389", bill_name: "Affordable Housing",
};

describe("corrections feed", () => {
  it("lists each correction with its record, reason and AI origin", async () => {
    vi.mocked(getCorrections).mockResolvedValueOnce([entry]);
    const res = await GET();
    const xml = await res.text();
    expect(res.headers.get("Content-Type")).toContain("application/rss+xml");
    expect(xml).toContain("<title>Sunshine Ledger — corrections</title>");
    expect(xml).toContain("H1389 — Affordable Housing</title>");
    expect(xml).toContain("https://sunshineledger.josephbernal.com/bills/b1#correction-c1");
    expect(xml).toContain("40% &lt;of units&gt;");
    expect(xml).toContain("AI-generated, not reviewed by a person");
    expect(xml).toContain(new Date(entry.decided_at).toUTCString());
  });

  it("fails rather than serving an empty feed when the log can't be loaded", async () => {
    vi.mocked(getCorrections).mockResolvedValueOnce(null);
    const res = await GET();
    expect(res.status).toBe(503);
  });

  it("is a valid empty feed when there are no corrections", async () => {
    vi.mocked(getCorrections).mockResolvedValueOnce([]);
    const xml = await (await GET()).text();
    expect(xml).toContain("<channel>");
    expect(xml).not.toContain("<item>");
  });
});
