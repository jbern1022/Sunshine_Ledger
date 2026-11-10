"use client";

import { useEffect, useRef, useState } from "react";

import {
  REGISTRATION_OPEN, answerTotp, confirmPasswordReset, confirmSignUp, deleteAccount, requestPasswordReset, resendConfirmation, signUp, exportData, getMe, getWatchlist, removeWatch, signIn, signOut, signOutEverywhere,
  type Me, type WatchItem,
} from "@/lib/account";
import { t, type MessageKey } from "@/lib/i18n";

const input = "mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm focus:border-sunshine-500 focus:outline-none focus:ring-1 focus:ring-sunshine-500";
const button = "rounded-md border border-sunshine-700 px-3 py-1.5 text-sm font-medium text-sunshine-700 hover:bg-sunshine-50 disabled:opacity-50";

const KNOWN_ERRORS = ["weak_password", "invalid_credentials", "mfa_required", "email_not_verified", "account_unavailable", "recovery_pending", "unavailable"];
const errorText = (code: string) => t(`account.err.${KNOWN_ERRORS.includes(code) ? code : "unavailable"}` as MessageKey);

type Mode = "signin" | "signup" | "confirm" | "reset" | "resetCode";

/** The step before sign-in: create an account, confirm the address, or reset a password. Every message here is
 *  the same whether or not the address has an account. */
function EntryForms({ mode, setMode, onMessage }: { mode: Exclude<Mode, "signin">; setMode: (m: Mode) => void; onMessage: (m: string) => void }) {
  const [email, setEmail] = useState("");
  const [secret, setSecret] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const addr = email.trim();
    let r: { ok: boolean; code?: string };
    if (mode === "signup") r = await signUp(addr, secret);
    else if (mode === "confirm") r = await confirmSignUp(addr, code.trim());
    else if (mode === "reset") r = await requestPasswordReset(addr);
    else r = await confirmPasswordReset(addr, code.trim(), secret);
    setBusy(false);
    setSecret("");
    setCode("");
    if (!r.ok) return setError(r.code ?? "unavailable");
    if (mode === "signup") setMode("confirm");
    else if (mode === "confirm") { onMessage(t("account.confirmed")); setMode("signin"); }
    else if (mode === "reset") setMode("resetCode");
    else { onMessage(t("account.resetDone")); setMode("signin"); }
  }

  const title = { signup: "account.createTitle", confirm: "account.confirmTitle", reset: "account.resetTitle", resetCode: "account.resetCodeTitle" }[mode] as MessageKey;
  const needsCode = mode === "confirm" || mode === "resetCode";
  const needsPassword = mode === "signup" || mode === "resetCode";
  return (
    <form onSubmit={submit} className="mt-4 max-w-sm">
      <h2 className="text-lg font-semibold text-ledger-900">{t(title)}</h2>
      {mode === "signup" && <p className="mt-1 text-xs text-slate-600">{t("account.createNote")}</p>}
      {mode === "confirm" && <p className="mt-1 text-xs text-slate-600">{t("account.confirmNote")}</p>}
      {mode === "reset" && <p className="mt-1 text-xs text-slate-600">{t("account.resetNote")}</p>}
      {error && <p role="alert" className="mt-2 rounded-md border border-red-300 bg-red-50 p-2 text-sm text-red-800">{errorText(error)}</p>}
      <div className="mt-3">
        <label htmlFor="ent-email" className="block text-sm font-medium text-ledger-900">{t("account.email")}</label>
        <input id="ent-email" className={input} type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
      </div>
      {needsCode && (
        <div className="mt-3">
          <label htmlFor="ent-code" className="block text-sm font-medium text-ledger-900">{t("account.confirmCode")}</label>
          <input id="ent-code" className={input} inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} required />
        </div>
      )}
      {needsPassword && (
        <div className="mt-3">
          <label htmlFor="ent-pw" className="block text-sm font-medium text-ledger-900">{t("account.newPassword")}</label>
          <input id="ent-pw" className={input} type="password" autoComplete="new-password" value={secret} onChange={(e) => setSecret(e.target.value)} required />
        </div>
      )}
      <button type="submit" disabled={busy} className={`mt-3 ${button}`}>{mode === "reset" ? t("account.resetSend") : t("account.continue")}</button>
      {mode === "confirm" && (
        <button type="button" className="ml-3 text-sm text-sunshine-700 underline" disabled={!email.trim()} onClick={async () => { await resendConfirmation(email.trim()); onMessage(t("account.resent")); }}>
          {t("account.resend")}
        </button>
      )}
      <p className="mt-3 text-sm"><button type="button" className="text-sunshine-700 underline" onClick={() => setMode("signin")}>{t("account.haveAccount")}</button></p>
    </form>
  );
}

function SignInForm({ onDone, setMode }: { onDone: () => void; setMode: (m: Mode) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [challenge, setChallenge] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const errorRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const r = challenge ? await answerTotp(challenge, code.trim()) : await signIn(email.trim(), password);
    setBusy(false);
    setPassword(""); // never keep the password in state longer than the request needs it
    setCode("");
    if (r.kind === "signed_in") return onDone();
    if (r.kind === "totp") return setChallenge(r.challengeToken);
    if (challenge && r.code === "invalid_credentials") setChallenge(null); // a failed code consumed the challenge: start again
    setError(r.code);
  }

  return (
    <form onSubmit={submit} className="mt-4 max-w-sm">
      <h2 className="text-lg font-semibold text-ledger-900">{t("account.signIn")}</h2>
      {error && (
        <p ref={errorRef} tabIndex={-1} role="alert" className="mt-2 rounded-md border border-red-300 bg-red-50 p-2 text-sm text-red-800">
          {errorText(error)}
        </p>
      )}
      {challenge ? (
        <div className="mt-3">
          <label htmlFor="acct-code" className="block text-sm font-medium text-ledger-900">{t("account.code")}</label>
          <p className="text-xs text-slate-500">{t("account.codeHelp")}</p>
          <input id="acct-code" className={input} inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} required />
        </div>
      ) : (
        <>
          <div className="mt-3">
            <label htmlFor="acct-email" className="block text-sm font-medium text-ledger-900">{t("account.email")}</label>
            <input id="acct-email" className={input} type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div className="mt-3">
            <label htmlFor="acct-password" className="block text-sm font-medium text-ledger-900">{t("account.password")}</label>
            <input id="acct-password" className={input} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
        </>
      )}
      <button type="submit" disabled={busy} className={`mt-3 ${button}`}>{t("account.continue")}</button>
      {!challenge && (
        <p className="mt-3 flex gap-4 text-sm">
          <button type="button" className="text-sunshine-700 underline" onClick={() => setMode("reset")}>{t("account.forgotLink")}</button>
          {REGISTRATION_OPEN && <button type="button" className="text-sunshine-700 underline" onClick={() => setMode("signup")}>{t("account.createLink")}</button>}
        </p>
      )}
    </form>
  );
}

export default function AccountPanel() {
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const [watch, setWatch] = useState<WatchItem[] | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("signin");

  async function load() {
    const m = await getMe();
    setMe(m);
    setWatch(m && !m.restricted ? await getWatchlist() : null);
  }
  useEffect(() => {
    void load();
  }, []);

  async function download() {
    const data = await exportData();
    if (!data) return setNotice(t("account.err.unavailable"));
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "sunshine-ledger-my-data.json";
    a.click();
    URL.revokeObjectURL(url);
  }
  async function afterSignOut(r: { ok: boolean }) {
    if (r.ok) {
      setMe(null);
      setWatch(null);
    }
  }
  async function reallyDelete() {
    const r = await deleteAccount();
    if (r.ok) {
      setConfirming(false);
      setMe(null);
      setNotice(t("account.deleted"));
    } else {
      setConfirming(false);
      setNotice(r.code === "reauth_required" ? t("account.deleteReauth") : t("account.err.unavailable"));
    }
  }

  return (
    <section aria-labelledby="account-heading">
      <h1 id="account-heading" className="text-2xl font-bold text-ledger-900">{t("account.title")}</h1>
      {notice && <p role="status" className="mt-3 rounded-md border border-slate-200 bg-slate-50 p-2 text-sm text-slate-800">{notice}</p>}
      {me === undefined && <p className="mt-3 text-sm text-slate-600">{t("account.loading")}</p>}
      {me === null && mode === "signin" && <SignInForm setMode={setMode} onDone={() => { setNotice(null); void load(); }} />}
      {me === null && mode !== "signin" && <EntryForms mode={mode} setMode={setMode} onMessage={setNotice} />}
      {me && (
        <div className="mt-3">
          <p className="text-sm text-slate-800">{t("account.signedInAs", { email: me.email ?? "—" })}</p>
          {me.restricted && <p className="mt-1 text-sm text-amber-800">{t("account.restricted")}</p>}
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" className={button} onClick={async () => afterSignOut(await signOut())}>{t("account.signOut")}</button>
            <button type="button" className={button} onClick={async () => afterSignOut(await signOutEverywhere())}>{t("account.signOutEverywhere")}</button>
          </div>

          {!me.restricted && (
            <section className="mt-6" aria-labelledby="watch-heading">
              <h2 id="watch-heading" className="text-lg font-semibold text-ledger-900">{t("account.watchlist")}</h2>
              <p className="text-xs text-slate-500">{t("account.watchlistFree")}</p>
              {watch && watch.length === 0 && <p className="mt-2 text-sm text-slate-600">{t("account.watchlistNone")}</p>}
              <ul className="mt-2 space-y-1 text-sm">
                {(watch ?? []).map((w) => (
                  <li key={w.id}>
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700">{t(`account.kind.${w.kind}` as MessageKey)}</span>{" "}
                    {w.target}{w.jurisdiction ? ` · ${w.jurisdiction}` : ""}{" "}
                    <button type="button" className="text-xs text-sunshine-700 underline" onClick={async () => { if (await removeWatch(w.id)) setWatch((cur) => (cur ?? []).filter((x) => x.id !== w.id)); }}>
                      {t("account.unfollow")}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="mt-6" aria-label={t("account.export")}>
            <button type="button" className={button} onClick={download}>{t("account.export")}</button>
            <p className="mt-1 text-xs text-slate-500">{t("account.exportNote")}</p>
          </section>

          {!me.restricted && (
            <section className="mt-6">
              {confirming ? (
                <div role="alertdialog" aria-labelledby="del-q" className="max-w-md rounded-md border border-red-300 bg-red-50 p-3">
                  <p id="del-q" className="text-sm text-red-900">{t("account.deleteConfirm")}</p>
                  <div className="mt-2 flex gap-2">
                    <button type="button" className="rounded-md border border-red-700 px-3 py-1.5 text-sm font-medium text-red-800 hover:bg-red-100" onClick={reallyDelete}>{t("account.deleteYes")}</button>
                    <button type="button" className={button} onClick={() => setConfirming(false)}>{t("account.deleteNo")}</button>
                  </div>
                </div>
              ) : (
                <button type="button" className="text-sm text-red-800 underline" onClick={() => setConfirming(true)}>{t("account.delete")}</button>
              )}
            </section>
          )}
        </div>
      )}
    </section>
  );
}
