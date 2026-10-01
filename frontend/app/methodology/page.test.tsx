import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import MethodologyPage from "./page";

describe("MethodologyPage", () => {
  it("explains the three layers and the review labels", () => {
    render(<MethodologyPage />);
    expect(screen.getByRole("heading", { name: "Bill Says, Interpretation, Expected Effect, Who it affects" })).toBeInTheDocument();
    // Bill Says quotes and Who it affects sentences are both checked.
    expect(screen.getAllByText(/checked word for word/)).toHaveLength(2);
    expect(screen.getByText(/an exception the bill doesn.t state is never/)).toBeInTheDocument();
    expect(screen.getByText(/A new version starts unreviewed/)).toBeInTheDocument();
    expect(screen.getByText(/Not yet evaluated/)).toBeInTheDocument();
  });
});
