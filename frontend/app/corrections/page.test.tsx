import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

const getCorrections = vi.fn();
vi.mock("@/lib/server-api", () => ({ getCorrections: (...args: unknown[]) => getCorrections(...args) }));

import CorrectionsPage from "./page";

async function renderPage(searchParams: Record<string, string> = {}) {
  render(await CorrectionsPage({ searchParams: Promise.resolve(searchParams) }));
}

describe("CorrectionsPage", () => {
  beforeEach(() => getCorrections.mockReset());

  it("says when nothing has been corrected yet", async () => {
    getCorrections.mockResolvedValue([]);
    await renderPage();
    expect(screen.getByText("No material or critical corrections have been published yet.")).toBeInTheDocument();
    expect(getCorrections).toHaveBeenCalledWith({ change_type: undefined, severity: "material" });
    expect(screen.getByRole("link", { name: "Follow by RSS" })).toHaveAttribute("href", "/corrections/feed.xml");
  });

  it("doesn't claim there are none when the API is down", async () => {
    getCorrections.mockResolvedValue(null);
    await renderPage();
    expect(screen.getByText(/couldn.t be loaded/)).toBeInTheDocument();
  });

  it("passes valid filters through, ignores bad ones, and links each entry to its bill", async () => {
    getCorrections.mockResolvedValue([{
      id: "c1", bill_entity_id: "b1", bill_number: "H1389", bill_name: "Affordable Housing", object_type: "page_copy",
      object_id: null, prior_version: null, current_version: null, prior_text: null, current_text: null,
      change_type: "clarification", severity: "critical", trigger: "internal_review", explanation: "Wording implied a vote.",
      evidence_links: [], origin: null, was_reviewed: null, methodology_version: null,
      decided_at: "2026-10-02T12:00:00Z", decided_by_label: "Sunshine Ledger editor",
    }]);
    await renderPage({ type: "clarification", severity: "critical" });
    expect(getCorrections).toHaveBeenCalledWith({ change_type: "clarification", severity: "critical" });
    expect(screen.getByRole("link", { name: "H1389 — Affordable Housing" })).toHaveAttribute("href", "/bills/b1#correction-c1");
    expect(screen.getByRole("link", { name: "Clarification" })).toHaveAttribute("aria-current", "page");

    getCorrections.mockClear();
    await renderPage({ type: "nonsense" });
    expect(getCorrections).toHaveBeenCalledWith({ change_type: undefined, severity: "material" });
  });
});
