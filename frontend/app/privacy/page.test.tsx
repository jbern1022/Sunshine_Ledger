import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import PrivacyPage from "./page";
import { SECURITY_REPORT_URL } from "@/lib/links";

// These statements are public commitments. The retention one is enforced by
// backend/app/pipeline/purge_flag_emails.py (RETENTION_DAYS) -- change both
// together or neither.
describe("PrivacyPage", () => {
  it("states the reporter-email retention period", () => {
    render(<PrivacyPage />);
    expect(screen.getByText(/deleted automatically\s+within 90 days after the report is resolved/)).toBeInTheDocument();
  });

  it("says it is not legal advice", () => {
    render(<PrivacyPage />);
    expect(screen.getByText(/Informational only, not legal advice/)).toBeInTheDocument();
  });

  it("discloses the Impact Lens session storage: what is kept, that it stays local, and how to clear it", () => {
    render(<PrivacyPage />);
    expect(screen.getByText(/role, county, municipality \(if you give one\) and property type/)).toBeInTheDocument();
    expect(screen.getByText(/never sent to our servers/)).toBeInTheDocument();
    expect(screen.getByText(/cleared when you close the tab/)).toBeInTheDocument();
    expect(screen.getByText(/Clear my answers/)).toBeInTheDocument();
  });

  it("discloses the OpenStreetMap tile requests", () => {
    render(<PrivacyPage />);
    expect(screen.getByRole("link", { name: /OpenStreetMap Foundation privacy policy/ })).toBeInTheDocument();
  });

  it("links to private security reporting", () => {
    render(<PrivacyPage />);
    expect(screen.getByRole("link", { name: /private vulnerability reporting/ })).toHaveAttribute(
      "href",
      SECURITY_REPORT_URL,
    );
  });
});
