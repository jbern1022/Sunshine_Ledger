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

  it("discloses browser storage and the OpenStreetMap tile requests", () => {
    render(<PrivacyPage />);
    expect(screen.getByText(/doesn.t use\s+local storage/)).toBeInTheDocument();
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
