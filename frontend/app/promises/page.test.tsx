import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

const getPromises = vi.fn();
vi.mock("@/lib/server-api", () => ({ getPromises: (...a: unknown[]) => getPromises(...a) }));
vi.mock("@/lib/api", () => ({ flagPromise: vi.fn() }));

import PromisesPage from "./page";

const item = (over: Record<string, unknown> = {}) => ({
  id: "p1",
  quote: "I will cut property taxes for every homeowner in our district.",
  source_url: "https://jane.example/issues",
  captured_at: "2026-11-10T00:00:00Z",
  review_state: "unreviewed",
  review_label: "Unreviewed",
  automated_labels: { automated: true, commitment_type: "commitment", topics: ["housing"] },
  snapshot: { id: "s1", fetched_at: "2026-11-10T12:00:00Z", content_hash: "a".repeat(64), internet_archive_capture: null },
  official: { name: "Jane Smith", chamber: "house", district: 3, party: "REP", result_status: "unofficial", office_status: null },
  ...over,
});

async function renderPage(sp: Record<string, string> = {}) {
  render(await PromisesPage({ searchParams: Promise.resolve(sp) }));
}

describe("PromisesPage", () => {
  beforeEach(() => getPromises.mockReset());

  it("shows the exact words, the Unreviewed label, the source and the disclosure", async () => {
    getPromises.mockResolvedValue({ disclosure: "Collected automatically.", total: 1, items: [item()] });
    await renderPage();
    expect(screen.getByText("I will cut property taxes for every homeowner in our district.")).toBeInTheDocument();
    expect(screen.getByText("Unreviewed")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Source" })).toHaveAttribute("href", "https://jane.example/issues");
    expect(screen.getByText("Collected automatically.")).toBeInTheDocument();
    expect(screen.getByText("Results not yet certified")).toBeInTheDocument();
    expect(screen.getByText(/Automated draft labels: commitment, housing/)).toBeInTheDocument();
    expect(screen.queryByText(/kept|broken|fulfilled/i)).not.toBeInTheDocument();
  });

  it("says so when nothing is collected, and when the API is down", async () => {
    getPromises.mockResolvedValue({ disclosure: "d", total: 0, items: [] });
    await renderPage();
    expect(screen.getByText("No statements have been collected yet.")).toBeInTheDocument();
    getPromises.mockResolvedValue(null);
    await renderPage();
    expect(screen.getByText(/couldn.t be loaded/)).toBeInTheDocument();
  });

  it("passes a valid chamber filter and ignores a bad one", async () => {
    getPromises.mockResolvedValue({ disclosure: "d", total: 0, items: [] });
    await renderPage({ chamber: "senate" });
    expect(getPromises).toHaveBeenLastCalledWith({ chamber: "senate" });
    await renderPage({ chamber: "nope" });
    expect(getPromises).toHaveBeenLastCalledWith({ chamber: undefined });
  });

  it("shows the left-office status instead of any verdict", async () => {
    getPromises.mockResolvedValue({
      disclosure: "d", total: 1,
      items: [item({ official: { name: "Pat Doe", chamber: "senate", district: 9, party: null, result_status: "certified", office_status: "Left office before outcome could be determined" } })],
    });
    await renderPage();
    expect(screen.getByText("Left office before outcome could be determined")).toBeInTheDocument();
  });
});
