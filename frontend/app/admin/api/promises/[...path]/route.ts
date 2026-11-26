/** Same-origin proxy for the promise-review page (docs/ADMIN_ACCESS_AUDIT.md).
 *
 *  Cloudflare Access fronts the API's /…/admin paths, so the browser can no
 *  longer call them cross-origin (Access answers with a login redirect). The
 *  page calls this route instead; it lives under /admin on the site, which
 *  Access protects, and forwards server-to-server over INTERNAL_API_URL,
 *  never through Cloudflare. Only the two review endpoints are forwarded, so
 *  this is not an open relay, and the reviewer's HTTP Basic credentials still
 *  go to the API's own check. */

const SERVER_API_URL =
  process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type Ctx = { params: Promise<{ path: string[] }> };

/** The API path for an allowed request, or null. */
export function upstreamPath(method: string, path: string[]): string | null {
  if (method === "GET" && path.length === 1 && path[0] === "queue") return "/promises/admin/queue";
  if (method === "POST" && path.length === 2 && UUID.test(path[0]) && path[1] === "review") {
    return `/promises/admin/${path[0]}/review`;
  }
  return null;
}

async function forward(req: Request, ctx: Ctx): Promise<Response> {
  const { path } = await ctx.params;
  const target = upstreamPath(req.method, path);
  if (!target) return new Response("Not found", { status: 404 });

  const headers: Record<string, string> = {};
  const auth = req.headers.get("authorization");
  if (auth) headers["Authorization"] = auth;
  // Who Cloudflare Access let in (audit gap 2). The API verifies this signed
  // token and records its email as the reviewer; the plain email header is
  // not trusted there, so it isn't forwarded.
  const accessJwt = req.headers.get("cf-access-jwt-assertion");
  if (accessJwt) headers["Cf-Access-Jwt-Assertion"] = accessJwt;
  if (req.method === "POST") headers["Content-Type"] = "application/json";

  const query = new URL(req.url).search;
  const res = await fetch(`${SERVER_API_URL}${target}${query}`, {
    method: req.method,
    headers,
    body: req.method === "POST" ? await req.text() : undefined,
    cache: "no-store",
  });
  return new Response(res.body, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("content-type") ?? "application/json", "Cache-Control": "no-store" },
  });
}

export const GET = forward;
export const POST = forward;
