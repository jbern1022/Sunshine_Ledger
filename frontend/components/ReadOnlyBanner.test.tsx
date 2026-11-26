import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ReadOnlyBanner, { READ_ONLY } from "./ReadOnlyBanner";

describe("ReadOnlyBanner", () => {
  it("is off unless the standby build sets NEXT_PUBLIC_READ_ONLY", () => {
    expect(READ_ONLY).toBe(false);
    const { container } = render(<ReadOnlyBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it("tells readers what still works when on", () => {
    render(<ReadOnlyBanner enabled />);
    const banner = screen.getByRole("status");
    expect(banner).toHaveTextContent(/backup copy/);
    expect(banner).toHaveTextContent(/reports, reviews and account changes are paused/);
  });
});
