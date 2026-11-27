import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

const getPublishedStatus = vi.fn();
vi.mock("@/lib/status", () => ({
  getPublishedStatus: () => getPublishedStatus(),
  STATUS_PAGE_URL: "https://status.example/",
}));

import StatusPage from "./page";

const STATUS = {
  generated_at: "2026-11-27T04:00:00+00:00", current: "up", measured_since: "2026-11-26T03:11+00:00",
  method: "Route 53 health checkers outside our network ...",
  windows: { "24h": { uptime_pct: 100, coverage_pct: 75, down_periods: 0 }, "90d": { uptime_pct: null, coverage_pct: 0, down_periods: 0 } },
  incidents: [{ start: "2026-11-26T14:10+00:00", end: "2026-11-26T19:49+00:00", minutes: 339, note: "Monitoring fault, not an outage." }],
  data: { reachable: true, last_ingest_at: "2026-11-26T05:57:11+00:00", sources_total: 37, sources_fresh: 36 },
};

describe("StatusPage", () => {
  beforeEach(() => getPublishedStatus.mockReset());

  it("shows uptime with coverage, incidents with notes, and freshness", async () => {
    getPublishedStatus.mockResolvedValue(STATUS);
    render(await StatusPage());
    expect(screen.getByText("Up", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText("100.00%")).toBeInTheDocument();
    expect(screen.getByText("75.0%")).toBeInTheDocument();
    expect(screen.getByText("no data")).toBeInTheDocument();
    expect(screen.getByText(/339 min\): Monitoring fault, not an outage/)).toBeInTheDocument();
    expect(screen.getByText(/36 of 37 sources/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "an independent status page" })).toHaveAttribute("href", "https://status.example/");
  });

  it("says so when the figures can't be loaded, instead of claiming all is well", async () => {
    getPublishedStatus.mockResolvedValue(null);
    render(await StatusPage());
    expect(screen.getByRole("status")).toHaveTextContent(/couldn.t be loaded/);
    expect(screen.queryByText("Up")).not.toBeInTheDocument();
  });
});
