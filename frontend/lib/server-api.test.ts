import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getBill,
  getPerson,
  getAllBillsForSitemap,
  getAllPeopleForSitemap,
  getRecentBillsForFeed,
} from "./server-api";
import type { BillDetail, BillListResponse, PersonDetail, PersonListResponse } from "./types";

// These are the two functions that actually publish content (sitemap.ts,
// feed.xml/route.ts degrade to an empty/partial result rather than fail the
// whole page when the API is unreachable) -- so "throws/errors are
// swallowed into a safe fallback" is the behavior worth pinning down here,
// not just the happy path.

function jsonResponse(body: unknown, ok = true): Response {
  return { ok, json: () => Promise.resolve(body) } as Response;
}

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

const baseBill: BillDetail = {
  entity_id: "bill-1",
  bill_number: "HB 123",
  name: "Test Bill",
  session: "2026 Regular Session",
  chamber: "House",
  status: "Introduced",
  jurisdiction_level: "state",
  jurisdiction_name: "FL",
  geo_scope_type: "statewide",
  geo_scope_names: ["FL"],
  introduced_date: null,
  last_action_date: null,
  what_it_does: null,
  source_count: 0,
  full_text_url: null,
  primary_sponsor: null,
  last_action: null,
  sponsors: [],
  claims: [],
  news: [],
  votes: [],
};

const basePerson: PersonDetail = {
  entity_id: "p1",
  name: "Jane Smith",
  district: null,
  role: null,
  party: null,
  jurisdiction_name: "FL",
  sponsored_count: 0,
  bills: [],
  votes: [],
};

describe("getBill", () => {
  it("returns the parsed bill on a successful fetch", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(baseBill));
    await expect(getBill("bill-1")).resolves.toEqual(baseBill);
  });

  it("returns null on a non-2xx response instead of throwing", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(null, false));
    await expect(getBill("missing")).resolves.toBeNull();
  });

  it("returns null when the fetch itself throws (API unreachable)", async () => {
    fetchMock.mockRejectedValueOnce(new Error("connect ECONNREFUSED"));
    await expect(getBill("bill-1")).resolves.toBeNull();
  });
});

describe("getPerson", () => {
  it("returns the parsed person on a successful fetch", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(basePerson));
    await expect(getPerson("p1")).resolves.toEqual(basePerson);
  });

  it("returns null on a non-2xx response instead of throwing", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(null, false));
    await expect(getPerson("missing")).resolves.toBeNull();
  });

  it("returns null when the fetch itself throws", async () => {
    fetchMock.mockRejectedValueOnce(new Error("connect ECONNREFUSED"));
    await expect(getPerson("p1")).resolves.toBeNull();
  });
});

function billPage(items: BillListResponse["items"], total: number): BillListResponse {
  return { total, items };
}

function makeBills(n: number, offset = 0): BillListResponse["items"] {
  return Array.from({ length: n }, (_, i) => ({
    entity_id: `bill-${offset + i}`,
    bill_number: `HB ${offset + i}`,
    name: "x",
    session: "2026",
    chamber: null,
    status: "Introduced",
    jurisdiction_level: "state",
    jurisdiction_name: "FL",
    geo_scope_type: "statewide",
    geo_scope_names: ["FL"],
    introduced_date: null,
    last_action_date: null,
    what_it_does: null,
    source_count: 0,
    full_text_url: null,
    primary_sponsor: null,
  }));
}

describe("getAllBillsForSitemap", () => {
  it("stops after one page when the first page is short", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(billPage(makeBills(3), 3)));

    const result = await getAllBillsForSitemap();

    expect(result).toHaveLength(3);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("pages through multiple full pages until the reported total is covered", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(billPage(makeBills(100, 0), 150)))
      .mockResolvedValueOnce(jsonResponse(billPage(makeBills(50, 100), 150)));

    const result = await getAllBillsForSitemap();

    expect(result).toHaveLength(150);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    // Confirms the offset actually advances between calls, not just that
    // two calls happened.
    expect(fetchMock.mock.calls[0][0]).toContain("offset=0");
    expect(fetchMock.mock.calls[1][0]).toContain("offset=100");
  });

  it("stops and returns what it has so far if a later page fails", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(billPage(makeBills(100, 0), 300)))
      .mockResolvedValueOnce(jsonResponse(null, false));

    const result = await getAllBillsForSitemap();

    expect(result).toHaveLength(100);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("stops at a network error mid-pagination rather than throwing", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(billPage(makeBills(100, 0), 300)))
      .mockRejectedValueOnce(new Error("timeout"));

    await expect(getAllBillsForSitemap()).resolves.toHaveLength(100);
  });

  it("stops at the 10,000-item hard ceiling even if the API keeps claiming more", async () => {
    // A real guard against a pagination bug hanging the sitemap route
    // forever -- always return a full page with an inflated total, so only
    // the hard ceiling (not a short page or the total) can end the loop.
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(billPage(makeBills(100), 999_999))));

    const result = await getAllBillsForSitemap();

    expect(result).toHaveLength(10_000);
    expect(fetchMock).toHaveBeenCalledTimes(100);
  });
});

describe("getAllPeopleForSitemap", () => {
  it("returns sponsor ids on success", async () => {
    const page: PersonListResponse = {
      total: 2,
      items: [
        { ...basePerson, entity_id: "p1" },
        { ...basePerson, entity_id: "p2" },
      ],
    };
    fetchMock.mockResolvedValueOnce(jsonResponse(page));

    await expect(getAllPeopleForSitemap()).resolves.toEqual(["p1", "p2"]);
  });

  it("returns an empty array on failure rather than breaking the sitemap build", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(null, false));
    await expect(getAllPeopleForSitemap()).resolves.toEqual([]);
  });

  it("returns an empty array when the fetch throws", async () => {
    fetchMock.mockRejectedValueOnce(new Error("timeout"));
    await expect(getAllPeopleForSitemap()).resolves.toEqual([]);
  });
});

describe("getRecentBillsForFeed", () => {
  it("returns items on success and requests the default limit of 50", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(billPage(makeBills(5), 5)));

    const result = await getRecentBillsForFeed();

    expect(result).toHaveLength(5);
    expect(fetchMock.mock.calls[0][0]).toContain("limit=50");
  });

  it("respects a custom limit", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(billPage(makeBills(5), 5)));

    await getRecentBillsForFeed(10);

    expect(fetchMock.mock.calls[0][0]).toContain("limit=10");
  });

  it("returns an empty array on failure rather than breaking the feed", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(null, false));
    await expect(getRecentBillsForFeed()).resolves.toEqual([]);
  });
});
