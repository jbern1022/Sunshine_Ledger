import { afterEach, describe, expect, it, vi } from "vitest";
import { isOfficialSource, pageKindFor, sendUsage } from "./usage";

describe("pageKindFor", () => {
  it.each([
    ["/", "home"],
    ["/bills", "browse"],
    ["/bills/0b3edc73-ca8f-40df-9d98-d15e73b41da6", "bill"],
    ["/people", "browse"],
    ["/people/abc", "person"],
    ["/districts/CD-012", "district"],
    ["/map", "map"],
    ["/methodology", "methodology"],
    ["/privacy", "other"],
    ["/admin/promises", "other"],
  ])("%s -> %s", (path, kind) => {
    expect(pageKindFor(path)).toBe(kind);
  });

  it("never returns anything from the path itself", () => {
    expect(pageKindFor("/bills/H1389")).not.toContain("H1389");
  });
});

describe("isOfficialSource", () => {
  it.each([
    "https://www.flsenate.gov/Session/Bill/2026/1389",
    "https://jaxcityc.legistar.com/LegislationDetail.aspx?ID=1",
    "https://www.congress.gov/bill/119th-congress/house-bill/3838",
    "https://clerk.house.gov/Votes/2026100",
  ])("counts %s", (href) => expect(isOfficialSource(href)).toBe(true));

  it.each(["https://example.com/flsenate.gov", "https://notflsenate.gov/x", "/bills/x", "not a url"])(
    "does not count %s",
    (href) => expect(isOfficialSource(href)).toBe(false),
  );
});

describe("sendUsage", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("sends nothing while switched off (the default)", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    sendUsage("page_view", "home");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("when switched on, sends only the event and page kind, without credentials", async () => {
    vi.stubEnv("NEXT_PUBLIC_USAGE_COUNTS_ENABLED", "true");
    vi.resetModules();
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const mod = await import("./usage");
    mod.sendUsage("bill_read", "bill");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/usage$/);
    expect(JSON.parse(init.body)).toEqual({ event: "bill_read", page_kind: "bill" });
    expect(init.credentials).toBe("omit");
  });

  it("sends nothing from an automated browser", async () => {
    vi.stubEnv("NEXT_PUBLIC_USAGE_COUNTS_ENABLED", "true");
    vi.resetModules();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    Object.defineProperty(navigator, "webdriver", { value: true, configurable: true });
    const mod = await import("./usage");
    mod.sendUsage("page_view", "home");
    expect(fetchMock).not.toHaveBeenCalled();
    Object.defineProperty(navigator, "webdriver", { value: false, configurable: true });
  });
});
