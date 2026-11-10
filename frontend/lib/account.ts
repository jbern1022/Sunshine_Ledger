/** Browser-side calls for reader accounts. The session is an HttpOnly cookie the browser sends on its own
 *  (`credentials: "include"`); this module never sees it. State-changing calls echo the readable `sl_csrf`
 *  cookie in `X-CSRF-Token` (double submit). Passwords and one-time codes are sent in the request body and
 *  are not stored, logged or kept in state longer than the form needs them. */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Accounts are off unless the build says otherwise; with the flag off the pages are 404 and nothing here runs. */
export const ACCOUNTS_ENABLED = process.env.NEXT_PUBLIC_AUTH_ENABLED === "true";
/** Public registration is its own switch (the API's REGISTRATION_OPEN); until both are on there is no sign-up link. */
export const REGISTRATION_OPEN = ACCOUNTS_ENABLED && process.env.NEXT_PUBLIC_REGISTRATION_OPEN === "true";

export interface Me {
  id: string;
  email: string | null;
  second_factor_required: boolean;
  restricted: boolean;
  factors: string[];
}
export interface WatchItem {
  id: string;
  kind: "bill" | "official" | "topic";
  target: string;
  jurisdiction: string | null;
}
export type SignInResult =
  | { kind: "signed_in" }
  | { kind: "totp"; challengeToken: string }
  | { kind: "failed"; code: string };

function csrfToken(): string {
  try {
    const m = document.cookie.match(/(?:^|;\s*)sl_csrf=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  } catch {
    return "";
  }
}

async function call(path: string, init: { method?: string; body?: unknown; csrf?: boolean } = {}): Promise<Response> {
  const headers: Record<string, string> = {};
  if (init.body !== undefined) headers["Content-Type"] = "application/json";
  if (init.csrf) headers["X-CSRF-Token"] = csrfToken();
  return fetch(`${API_URL}${path}`, {
    method: init.method ?? "GET",
    headers,
    credentials: "include",
    cache: "no-store",
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
}

async function failureCode(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return typeof body?.detail === "string" ? body.detail : "unavailable";
  } catch {
    return "unavailable";
  }
}

export async function getMe(): Promise<Me | null> {
  try {
    const res = await call("/auth/me");
    return res.ok ? res.json() : null;
  } catch {
    return null;
  }
}

export async function signIn(email: string, password: string): Promise<SignInResult> {
  try {
    const res = await call("/auth/sign-in", { method: "POST", body: { email, password } });
    if (!res.ok) return { kind: "failed", code: await failureCode(res) };
    const body = await res.json();
    return body.signed_in ? { kind: "signed_in" } : { kind: "totp", challengeToken: body.challenge_token };
  } catch {
    return { kind: "failed", code: "unavailable" };
  }
}

export async function answerTotp(challengeToken: string, code: string): Promise<SignInResult> {
  try {
    const res = await call("/auth/totp", { method: "POST", body: { challenge_token: challengeToken, code } });
    return res.ok ? { kind: "signed_in" } : { kind: "failed", code: await failureCode(res) };
  } catch {
    return { kind: "failed", code: "unavailable" };
  }
}

type Outcome = { ok: boolean; code?: string };

async function postJson(path: string, body: unknown): Promise<Outcome> {
  try {
    const res = await call(path, { method: "POST", body });
    return res.ok ? { ok: true } : { ok: false, code: await failureCode(res) };
  } catch {
    return { ok: false, code: "unavailable" };
  }
}

export const signUp = (email: string, password: string) => postJson("/auth/sign-up", { email, password });
export const confirmSignUp = (email: string, code: string) => postJson("/auth/sign-up/confirm", { email, code });
export const resendConfirmation = (email: string) => postJson("/auth/sign-up/resend", { email });
export const requestPasswordReset = (email: string) => postJson("/auth/password-reset/request", { email });

export async function confirmPasswordReset(email: string, code: string, newPassword: string): Promise<{ ok: boolean; code?: string }> {
  try {
    const res = await call("/auth/password-reset/confirm", { method: "POST", body: { email, code, new_password: newPassword } });
    return res.ok ? { ok: true } : { ok: false, code: await failureCode(res) };
  } catch {
    return { ok: false, code: "unavailable" };
  }
}

async function simplePost(path: string): Promise<{ ok: boolean; code?: string; body?: Record<string, unknown> }> {
  try {
    const res = await call(path, { method: "POST", csrf: true });
    return res.ok ? { ok: true, body: await res.json() } : { ok: false, code: await failureCode(res) };
  } catch {
    return { ok: false, code: "unavailable" };
  }
}

export const signOut = () => simplePost("/auth/sign-out");
export const signOutEverywhere = () => simplePost("/auth/sign-out-all");
export const deleteAccount = () => simplePost("/auth/me/delete");

export async function exportData(): Promise<unknown | null> {
  try {
    const res = await call("/auth/me/export");
    return res.ok ? res.json() : null;
  } catch {
    return null;
  }
}

export async function getWatchlist(): Promise<WatchItem[] | null> {
  try {
    const res = await call("/watchlist");
    return res.ok ? (await res.json()).items : null;
  } catch {
    return null;
  }
}

export async function addWatch(kind: WatchItem["kind"], target: string, jurisdiction = ""): Promise<{ ok: boolean; message?: string }> {
  try {
    const res = await call("/watchlist", { method: "POST", csrf: true, body: { kind, target, jurisdiction } });
    return res.ok ? { ok: true } : { ok: false, message: await failureCode(res) };
  } catch {
    return { ok: false, message: "unavailable" };
  }
}

export async function removeWatch(id: string): Promise<boolean> {
  const r = await simplePost(`/watchlist/${id}/remove`);
  return r.ok;
}
