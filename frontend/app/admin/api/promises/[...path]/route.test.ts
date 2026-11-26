import { afterEach, describe, expect, it, vi } from "vitest";
import { GET, POST, upstreamPath } from "./route";

const ID = "0b3edc73-ca8f-40df-9d98-d15e73b41da6";
const ctx = (path: string[]) => ({ params: Promise.resolve({ path }) });

describe("upstreamPath", () => {
  it("allows only the queue and a review of one statement", () => {
    expect(upstreamPath("GET", ["queue"])).toBe("/promises/admin/queue");
    expect(upstreamPath("POST", [ID, "review"])).toBe(`/promises/admin/${ID}/review`);
  });

  it.each([
    ["GET", ["..", "..", "bills"]],
    ["GET", [ID, "review"]],
    ["POST", ["queue"]],
    ["POST", ["not-a-uuid", "review"]],
    ["GET", ["queue", "extra"]],
  ])("refuses %s %j", (method, path) => {
    expect(upstreamPath(method, path as string[])).toBeNull();
  });
});

describe("proxy", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("forwards the queue request with the reviewer's credentials and query", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{"total":0,"items":[]}', { status: 200, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    const req = new Request("http://site/admin/api/promises/queue?limit=50", {
      headers: { Authorization: "Basic abc", "Cf-Access-Authenticated-User-Email": "admin@example.org", Cookie: "x=1" },
    });
    const res = await GET(req, ctx(["queue"]));
    expect(res.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/promises\/admin\/queue\?limit=50$/);
    expect(init.headers.Authorization).toBe("Basic abc");
    expect(init.headers["Cf-Access-Authenticated-User-Email"]).toBe("admin@example.org");
    expect(init.headers.Cookie).toBeUndefined();
  });

  it("passes the API's 401 through", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("no", { status: 401 })));
    const res = await GET(new Request("http://site/admin/api/promises/queue"), ctx(["queue"]));
    expect(res.status).toBe(401);
  });

  it("answers 404 without calling the API for anything else", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const res = await POST(new Request("http://site/admin/api/promises/x", { method: "POST", body: "{}" }), ctx(["x"]));
    expect(res.status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
