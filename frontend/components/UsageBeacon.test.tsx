import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import UsageBeacon from "./UsageBeacon";

vi.mock("next/navigation", () => ({ usePathname: () => "/bills/abc" }));

describe("UsageBeacon", () => {
  it("renders nothing and makes no request while switched off", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { container } = render(<UsageBeacon />);
    expect(container).toBeEmptyDOMElement();
    expect(fetchMock).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
