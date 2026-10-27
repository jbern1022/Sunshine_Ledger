import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "./proxy";

const request = (url = "http://localhost:3000/", headers: Record<string, string> = {}, cookie?: string) =>
  new NextRequest(url, { headers: { ...headers, ...(cookie ? { cookie } : {}) } });

/** ip-api answers with `geo`; /sources/status answers with `sources` (or fails when null). */
function stubFetch(geo: object | null, sources: object[] | null = null) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("ip-api.com")) {
      if (geo === null) throw new Error("timeout");
      return new Response(JSON.stringify(geo));
    }
    if (sources === null) return new Response("nope", { status: 503 });
    return new Response(JSON.stringify(sources));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const florida = (city: string) => ({ status: "success", countryCode: "US", regionName: "Florida", city });
const setCookie = (res: Response) => res.headers.get("set-cookie") ?? "";
const redirectTarget = (res: Response) => (res.headers.get("location") ? new URL(res.headers.get("location")!) : null);

describe("location default", () => {
  beforeEach(() => vi.unstubAllGlobals());
  afterEach(() => vi.unstubAllGlobals());

  it("does nothing, and makes no lookup, once the visit has been resolved", async () => {
    const f = stubFetch(florida("Miami"));
    const res = await proxy(request("http://localhost:3000/", { "x-forwarded-for": "1.2.3.4" }, "sl_geo_resolved=1"));
    expect(redirectTarget(res)).toBeNull();
    expect(f).not.toHaveBeenCalled();
  });

  it("does nothing when the reader already chose a jurisdiction", async () => {
    const f = stubFetch(florida("Miami"));
    const res = await proxy(request("http://localhost:3000/?jurisdiction=Key%20West", { "x-forwarded-for": "1.2.3.4" }));
    expect(redirectTarget(res)).toBeNull();
    expect(f).not.toHaveBeenCalled();
  });

  it("without a client IP (local dev) passes through and remembers it did", async () => {
    stubFetch(florida("Miami"));
    const res = await proxy(request());
    expect(redirectTarget(res)).toBeNull();
    expect(setCookie(res)).toContain("sl_geo_resolved=1");
  });

  it("sends a visitor in a covered city to that city, flagged as auto-detected", async () => {
    stubFetch(florida("Jacksonville"), [{ jurisdiction: "FL" }, { jurisdiction: "Jacksonville" }]);
    const res = await proxy(request("http://localhost:3000/", { "cf-connecting-ip": "5.6.7.8" }));
    const to = redirectTarget(res)!;
    expect(to.pathname).toBe("/");
    expect(to.searchParams.get("jurisdiction")).toBe("Jacksonville");
    expect(to.searchParams.get("auto")).toBe("1");
    expect(setCookie(res)).toContain("sl_geo_resolved=1");
  });

  it("matches the city case-insensitively and uses the first address in X-Forwarded-For", async () => {
    const f = stubFetch(florida("FORT LAUDERDALE"), [{ jurisdiction: "Fort Lauderdale" }]);
    const res = await proxy(request("http://localhost:3000/", { "x-forwarded-for": "9.9.9.9, 10.0.0.1" }));
    expect(redirectTarget(res)!.searchParams.get("jurisdiction")).toBe("Fort Lauderdale");
    expect(String(f.mock.calls[0][0])).toContain("/json/9.9.9.9?");
  });

  it("prefers the Cloudflare address over X-Forwarded-For", async () => {
    const f = stubFetch(florida("Miami"), [{ jurisdiction: "Miami" }]);
    await proxy(request("http://localhost:3000/", { "cf-connecting-ip": "5.6.7.8", "x-forwarded-for": "9.9.9.9" }));
    expect(String(f.mock.calls[0][0])).toContain("/json/5.6.7.8?");
  });

  it("gives a Florida visitor in an uncovered city the state view", async () => {
    stubFetch(florida("Tallahassee"), [{ jurisdiction: "Miami" }]);
    const res = await proxy(request("http://localhost:3000/", { "x-forwarded-for": "1.2.3.4" }));
    expect(redirectTarget(res)!.searchParams.get("jurisdiction")).toBe("FL");
  });

  it("falls back to the built-in city list when the source list is unreachable", async () => {
    stubFetch(florida("Key West"), null);
    const res = await proxy(request("http://localhost:3000/", { "x-forwarded-for": "1.2.3.4" }));
    expect(redirectTarget(res)!.searchParams.get("jurisdiction")).toBe("Key West");
  });

  it("does not redirect a visitor outside Florida or outside the US", async () => {
    stubFetch({ status: "success", countryCode: "US", regionName: "Georgia", city: "Atlanta" });
    expect(redirectTarget(await proxy(request("http://localhost:3000/", { "x-forwarded-for": "1.2.3.4" })))).toBeNull();
    stubFetch({ status: "success", countryCode: "CA", regionName: "Ontario", city: "Toronto" });
    expect(redirectTarget(await proxy(request("http://localhost:3000/", { "x-forwarded-for": "1.2.3.4" })))).toBeNull();
  });

  it("does not redirect when the lookup fails or is unsuccessful, and still sets the cookie", async () => {
    stubFetch(null);
    const failed = await proxy(request("http://localhost:3000/", { "x-forwarded-for": "1.2.3.4" }));
    expect(redirectTarget(failed)).toBeNull();
    expect(setCookie(failed)).toContain("sl_geo_resolved=1");

    stubFetch({ status: "fail" });
    expect(redirectTarget(await proxy(request("http://localhost:3000/", { "x-forwarded-for": "1.2.3.4" })))).toBeNull();
  });
});
