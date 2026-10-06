import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ImpactLens from "./ImpactLens";
import * as api from "@/lib/api";
import type { ImpactLensResponse, LensEntry } from "@/lib/impactLens";

vi.mock("@/lib/api", () => ({ fetchImpactLens: vi.fn() }));

const crit = (over = {}) => ({
  entry_index: 0, vocabulary_version: 2, relevance: "direct" as const, audience: null, affected: null,
  requires: [], excludes: [], unmapped: [], ambiguous: null, ...over,
});
const entry = (group: string, criteria: unknown, over: Partial<LensEntry> = {}): LensEntry => ({
  group, text: `${group} must comply`, quote: `Quote for ${group}.`, conditions: [{ text: "Applies in Duval County.", quote: "q" }],
  exceptions: [], criteria: criteria as LensEntry["criteria"], reviewed: false, ...over,
});

const base: ImpactLensResponse = {
  bill_entity_id: "b1", available: true, unavailable_reason: null, vocabulary_version: 2, complete: true, incomplete_reasons: [],
  layer: null,
  entries: [
    entry("Tenants", crit({ audience: { kind: "attr", attr: "role", any_of: ["renter"] },
      requires: [{ attr: "jurisdiction", op: "in", values: ["county:Duval"], from: { kind: "condition", index: 0 } }] })),
    entry("Anyone", crit({ audience: { kind: "anyone" } }), { conditions: [] }),
  ],
  questions: [
    { key: "role", label: "Role", question: "Which best describes you in relation to this bill?",
      options: [{ value: "renter", label: "Renter" }, { value: "none_of_these", label: "None of These" }] },
    { key: "county", label: "County", question: "Which Florida county do you live in?",
      options: [...["Duval", "Orange", "Leon", "Lee", "Polk", "Bay", "Clay", "Lake", "Levy"].map((c) => ({ value: c, label: `${c} County` }))] },
  ],
};

beforeEach(() => {
  vi.mocked(api.fetchImpactLens).mockReset();
  window.sessionStorage.clear();
});

describe("ImpactLens", () => {
  it("asks nothing and fetches nothing until the reader says yes", () => {
    render(<ImpactLens billEntityId="b1" />);
    expect(screen.getByText("Do you want to see if you may be impacted?")).toBeInTheDocument();
    expect(api.fetchImpactLens).not.toHaveBeenCalled();
    expect(screen.queryByRole("radio")).toBeNull();
  });

  it("walks role then county, then shows the result, the why chain and the Anyone line", async () => {
    vi.mocked(api.fetchImpactLens).mockResolvedValue(base);
    const user = userEvent.setup();
    render(<ImpactLens billEntityId="b1" />);
    await user.click(screen.getByRole("button", { name: "Yes, check" }));
    expect(await screen.findByText("Which best describes you in relation to this bill?")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Can't Determine");

    await user.click(screen.getByRole("radio", { name: "Renter" }));
    const county = await screen.findByLabelText("Which Florida county do you live in?");
    await user.selectOptions(county, "Duval");

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Applies to You"));
    expect(screen.getByText("Quote for Tenants.")).toBeInTheDocument();
    expect(screen.getByText("Role: Renter · Duval County")).toBeInTheDocument(); // labels, not raw values
    expect(screen.queryByText(/local_government|none_of_these/)).toBeNull();
    expect(screen.getByText("Applies to everyone")).toBeInTheDocument();
    expect(screen.getByText("Anyone:")).toBeInTheDocument(); // the group leads each line
    expect(screen.getByText("Automatically mapped, not yet reviewed by a person.")).toBeInTheDocument();
    expect(screen.getByText(/not legal or financial advice/)).toBeInTheDocument();
    // answers live in this browser only
    expect(JSON.parse(window.sessionStorage.getItem("impactLens.answers.v1") ?? "{}")).toEqual({ role: "renter", county: "Duval" });
  });

  it("None of These is an answer: it settles the role question for a bill that names other roles", async () => {
    vi.mocked(api.fetchImpactLens).mockResolvedValue(base);
    const user = userEvent.setup();
    render(<ImpactLens billEntityId="b1" />);
    await user.click(screen.getByRole("button", { name: "Yes, check" }));
    await user.click(await screen.findByRole("radio", { name: "None of These" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Does Not Appear to Apply"));
    expect(screen.getByRole("status")).toHaveTextContent(/not a guarantee/);
  });

  it("an incomplete list says so and never claims Does Not Appear to Apply", async () => {
    vi.mocked(api.fetchImpactLens).mockResolvedValue({ ...base, complete: false, incomplete_reasons: ["The analysis lists only the first entries of a longer list."] });
    const user = userEvent.setup();
    render(<ImpactLens billEntityId="b1" />);
    await user.click(screen.getByRole("button", { name: "Yes, check" }));
    await user.click(await screen.findByRole("radio", { name: "None of These" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Can't Determine"));
    expect(screen.getByText(/may not be complete: The analysis lists only the first entries/)).toBeInTheDocument();
  });

  it("restores answers from this session, lets you change one, and clears them all", async () => {
    window.sessionStorage.setItem("impactLens.answers.v1", JSON.stringify({ role: "renter", county: "Duval", evil: "x" }));
    vi.mocked(api.fetchImpactLens).mockResolvedValue(base);
    const user = userEvent.setup();
    render(<ImpactLens billEntityId="b1" />);
    await user.click(screen.getByRole("button", { name: "Yes, check" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Applies to You"));

    await user.click(screen.getByRole("button", { name: "Change County" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Can't Determine"));

    await user.click(screen.getByRole("button", { name: "Clear my answers" }));
    expect(window.sessionStorage.getItem("impactLens.answers.v1")).toBeNull();
    expect(screen.queryByText(/Your answers:/)).toBeNull();
  });

  it("a bill with no analysis says so", async () => {
    vi.mocked(api.fetchImpactLens).mockResolvedValue({ ...base, available: false, unavailable_reason: "This bill has no Who it affects analysis yet.", entries: [], questions: [] });
    const user = userEvent.setup();
    render(<ImpactLens billEntityId="b1" />);
    await user.click(screen.getByRole("button", { name: "Yes, check" }));
    expect(await screen.findByText("This bill has no Who it affects analysis yet.")).toBeInTheDocument();
  });

  it("a failed load says so without crashing", async () => {
    vi.mocked(api.fetchImpactLens).mockRejectedValue(new Error("boom"));
    const user = userEvent.setup();
    render(<ImpactLens billEntityId="b1" />);
    await user.click(screen.getByRole("button", { name: "Yes, check" }));
    expect(await screen.findByText(/could not load this bill's questions/)).toBeInTheDocument();
  });

  it("shows the open question when the text is ambiguous", async () => {
    const ambiguous: ImpactLensResponse = {
      ...base,
      entries: [entry("Counties", crit({ audience: { kind: "attr", attr: "role", any_of: ["renter"] }, ambiguous: { question: "Does the setback or the height cap control?", quote: "q-amb" } }), { conditions: [] })],
    };
    vi.mocked(api.fetchImpactLens).mockResolvedValue(ambiguous);
    const user = userEvent.setup();
    render(<ImpactLens billEntityId="b1" />);
    await user.click(screen.getByRole("button", { name: "Yes, check" }));
    await user.click(await screen.findByRole("radio", { name: "Renter" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Text Is Ambiguous Here"));
    expect(screen.getByText(/Does the setback or the height cap control\?/)).toBeInTheDocument();
  });
});
