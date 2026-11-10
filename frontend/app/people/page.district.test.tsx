import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import PeoplePage from "./page";
import * as api from "@/lib/api";

vi.mock("@/lib/api", () => ({ fetchPeople: vi.fn() }));
const { params } = vi.hoisted(() => ({ params: { current: "" } }));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(params.current) }));

const person = { entity_id: "a", name: "Pat Doe", district: "HD-045", role: "Rep", party: "REP", jurisdiction_name: "FL", sponsored_count: 3 };

describe("PeoplePage with ?district=", () => {
  beforeEach(() => vi.mocked(api.fetchPeople).mockReset());

  it("passes a valid district to the API and says whose members are shown", async () => {
    params.current = "district=HD-045";
    vi.mocked(api.fetchPeople).mockResolvedValue({ total: 1, items: [person] });
    render(<PeoplePage />);
    await screen.findByText("Pat Doe");
    expect(api.fetchPeople).toHaveBeenLastCalledWith(expect.objectContaining({ district: "HD-045" }));
    expect(screen.getByText(/Showing current and former members of HD-045/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Show everyone" })).toHaveAttribute("href", "/people");
  });

  it("ignores a malformed district", async () => {
    params.current = "district=nonsense";
    vi.mocked(api.fetchPeople).mockResolvedValue({ total: 1, items: [person] });
    render(<PeoplePage />);
    await screen.findByText("Pat Doe");
    expect(api.fetchPeople).toHaveBeenLastCalledWith(expect.objectContaining({ district: undefined }));
  });
});
