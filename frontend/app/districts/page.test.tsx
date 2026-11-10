import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

const getDistricts = vi.fn();
vi.mock("@/lib/server-api", () => ({ getDistricts: () => getDistricts() }));

import DistrictsPage from "./page";

describe("DistrictsPage", () => {
  beforeEach(() => getDistricts.mockReset());

  it("lists districts by chamber, each linking to its page, and names the map plan", async () => {
    getDistricts.mockResolvedValue({
      map_plan: { key: "k", name: "Plan 2022", effective_from: "2022-11-08" },
      total: 2,
      items: [{ code: "HD-001", chamber: "house", number: 1 }, { code: "SD-001", chamber: "senate", number: 1 }],
    });
    render(await DistrictsPage());
    expect(screen.getByRole("link", { name: "HD-001" })).toHaveAttribute("href", "/districts/HD-001");
    expect(screen.getByRole("link", { name: "SD-001" })).toHaveAttribute("href", "/districts/SD-001");
    expect(screen.getByText(/Plan 2022/)).toBeInTheDocument();
  });

  it("says so when districts can't be loaded", async () => {
    getDistricts.mockResolvedValue(null);
    render(await DistrictsPage());
    expect(screen.getByText(/couldn.t be loaded/)).toBeInTheDocument();
  });
});
