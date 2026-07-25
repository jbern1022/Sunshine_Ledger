import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// BRD 5.6: default the homepage to the visitor's likely state/locality via
// IP geolocation, while always letting them navigate elsewhere regardless
// of what was detected (the browse page's jurisdiction dropdown already
// covers that; this just sets the *initial* value once per visit).
//
// Runs once per browser (tracked via the `sl_geo_resolved` cookie) so a
// user who manually picks "All jurisdictions" doesn't get redirected back
// to their detected city on the next page load.

const GEO_RESOLVED_COOKIE = "sl_geo_resolved";
const GEO_LOOKUP_TIMEOUT_MS = 1500;

const CITY_JURISDICTIONS = ["Miami", "Jacksonville"];

export const config = {
  matcher: "/",
};

function extractClientIp(request: NextRequest): string | null {
  // Behind the planned Cloudflare Tunnel deployment (BRD 6), Cloudflare sets
  // CF-Connecting-IP to the real visitor IP. Fall back to the more generic
  // X-Forwarded-For for other reverse-proxy setups. Neither is present for
  // direct/local access, which is the expected no-op case in dev.
  const cf = request.headers.get("cf-connecting-ip");
  if (cf) return cf;

  const forwardedFor = request.headers.get("x-forwarded-for");
  if (forwardedFor) return forwardedFor.split(",")[0].trim();

  return null;
}

async function lookupJurisdiction(ip: string): Promise<string | null> {
  try {
    const res = await fetch(`http://ip-api.com/json/${ip}?fields=status,countryCode,regionName,city`, {
      signal: AbortSignal.timeout(GEO_LOOKUP_TIMEOUT_MS),
    });
    if (!res.ok) return null;

    const data = await res.json();
    if (data.status !== "success" || data.countryCode !== "US" || data.regionName !== "Florida") {
      return null;
    }

    const city = CITY_JURISDICTIONS.find((c) => c.toLowerCase() === String(data.city).toLowerCase());
    return city ?? "FL";
  } catch {
    return null; // geolocation is a nice-to-have default, never block the page on it
  }
}

export async function middleware(request: NextRequest) {
  if (request.cookies.has(GEO_RESOLVED_COOKIE) || request.nextUrl.searchParams.has("jurisdiction")) {
    return NextResponse.next();
  }

  const ip = extractClientIp(request);
  const jurisdiction = ip ? await lookupJurisdiction(ip) : null;

  const response = jurisdiction
    ? NextResponse.redirect(new URL(`/?jurisdiction=${encodeURIComponent(jurisdiction)}&auto=1`, request.url))
    : NextResponse.next();

  response.cookies.set(GEO_RESOLVED_COOKIE, "1", { maxAge: 60 * 60 * 24, sameSite: "lax" });
  return response;
}
