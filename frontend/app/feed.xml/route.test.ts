import { describe, it, expect, vi } from "vitest";

vi.mock("@/lib/server-api", () => ({ getRecentBillsForFeed: vi.fn() }));

import { getRecentBillsForFeed } from "@/lib/server-api";
import { GET } from "./route";
import type { BillListItem } from "@/lib/types";

const bill = (over: Partial<BillListItem> = {}): BillListItem => ({
  entity_id: "b1",
  bill_number: "H1389",
  name: "Affordable Housing",
  session: "2026 Regular Session",
  chamber: "House",
  status: "Introduced",
  jurisdiction_level: "state",
  jurisdiction_name: "FL",
  geo_scope_type: "statewide",
  geo_scope_names: ["FL"],
  introduced_date: null,
  last_action_date: "2026-10-02",
  what_it_does: "Limits <rent> increases & more.",
  source_count: 0,
  full_text_url: null,
  primary_sponsor: null,
  tags: [],
  ...over,
});

const feed = async (bills: BillListItem[]) => {
  vi.mocked(getRecentBillsForFeed).mockResolvedValueOnce(bills);
  const res = await GET();
  return { res, xml: await res.text() };
};

describe("bill feed", () => {
  it("lists each bill with its summary (escaped), link and last-action date", async () => {
    const { res, xml } = await feed([bill()]);
    expect(res.headers.get("Content-Type")).toContain("application/rss+xml");
    expect(xml).toContain("<title>H1389 — FL</title>");
    expect(xml).toContain("<link>https://sunshineledger.josephbernal.com/bills/b1</link>");
    expect(xml).toContain("Limits &lt;rent&gt; increases &amp; more.");
    expect(xml).toContain(`<pubDate>${new Date("2026-10-02").toUTCString()}</pubDate>`);
  });

  it("says when a bill has no summary yet, and omits pubDate when there is no action date", async () => {
    const { xml } = await feed([bill({ what_it_does: null, last_action_date: null })]);
    expect(xml).toContain("No plain-language summary has been generated yet.");
    expect(xml).not.toContain("<pubDate>");
  });

  it("states that summaries are AI-generated in the channel description", async () => {
    const { xml } = await feed([]);
    expect(xml).toContain("Summaries are AI-generated and are not individually reviewed by a person");
  });

  // Pins what the feed is today: one item per bill, keyed by the bill's URL.
  // A new action, amendment or vote changes the bill's pubDate (when the action
  // date moves) but not its guid, and the item text is the bill summary, not the
  // event, so many readers will not announce it again. Treat the feed as
  // "bills recently active", not as a change alert, until that is designed
  // (Todoist 6hWPfQqX443vpgCp).
  it("keys an item by the bill URL, so later activity on the same bill keeps its guid", async () => {
    const before = (await feed([bill({ last_action_date: "2026-10-02" })])).xml;
    const after = (await feed([bill({ last_action_date: "2026-10-20", status: "Passed" })])).xml;
    const guid = "<guid isPermaLink=\"true\">https://sunshineledger.josephbernal.com/bills/b1</guid>";
    expect(before).toContain(guid);
    expect(after).toContain(guid);
    expect(after).not.toContain("Passed");
  });
});
