import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import MethodologyPage from "./page";

describe("MethodologyPage", () => {
  it("explains the three layers and the review labels", () => {
    render(<MethodologyPage />);
    expect(screen.getByRole("heading", { name: "Bill Says, Interpretation, Expected Effect" })).toBeInTheDocument();
    expect(screen.getByText(/checked word for word/)).toBeInTheDocument();
    expect(screen.getAllByText(/reviewed by a person/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Not yet evaluated/)).toBeInTheDocument();
  });
});
