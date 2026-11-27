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

  it("explains the correction labels and links the log", () => {
    render(<MethodologyPage />);
    expect(screen.getByText(/Disputed — under review:/)).toBeInTheDocument();
    expect(screen.getByText(/filing a complaint can.t/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "corrections log" })).toHaveAttribute("href", "/corrections");
  });

  it("publishes the evidence signing key and how to verify", () => {
    render(<MethodologyPage />);
    expect(screen.getByRole("heading", { name: "Preserved evidence and how to check it" })).toBeInTheDocument();
    expect(screen.getByLabelText("Evidence signing public key").textContent).toMatch(/^-----BEGIN PUBLIC KEY-----/);
    expect(screen.getByText(/openssl dgst -sha256 -verify/)).toBeInTheDocument();
    expect(screen.getByText(/available on request/)).toBeInTheDocument();
  });
});
