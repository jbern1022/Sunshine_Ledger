"use client";

import { useState } from "react";
import QRCode from "qrcode";

import { finishTotpSetup, startTotpSetup } from "@/lib/account";
import { t, type MessageKey } from "@/lib/i18n";

const button = "rounded-md border border-sunshine-700 px-3 py-1.5 text-sm font-medium text-sunshine-700 hover:bg-sunshine-50 disabled:opacity-50";
const input = "mt-1 block w-full max-w-xs rounded-md border border-slate-300 px-2 py-1 text-sm";
const KNOWN = ["invalid_credentials", "mfa_already_enabled", "unavailable"];

function errorText(code: string): string {
  return t(`account.err.${KNOWN.includes(code) ? code : "unavailable"}` as MessageKey);
}

/** The key in groups of four, for typing into an app by hand. */
export function groupKey(secret: string): string {
  return secret.replace(/(.{4})(?=.)/g, "$1 ");
}

/** Turn on an authenticator app (TOTP): re-enter the password, scan a code (drawn here in the browser; the
 *  secret never goes to a third-party service), prove one code, then sign in again with it. Optional for
 *  readers; the secret lives only in this component's state until the step finishes. */
export default function TotpSetup({ onSignedOut }: { onSignedOut: () => void }) {
  const [step, setStep] = useState<"offer" | "password" | "scan">("offer");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [secret, setSecret] = useState<{ key: string; uri: string } | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function begin(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    const r = await startTotpSetup(password);
    setBusy(false);
    setPassword("");
    if (!r.ok) return setError(errorText(r.code));
    setError(null);
    setSecret({ key: r.secret, uri: r.uri });
    // Drawn here, in the browser; if it fails the typed key below still works.
    setQr(await QRCode.toDataURL(r.uri, { margin: 1, width: 192 }).catch(() => null));
    setStep("scan");
  }

  async function finish(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    const r = await finishTotpSetup(password, code.trim());
    setBusy(false);
    setPassword("");
    setCode("");
    if (!r.ok) return setError(errorText(r.code ?? "unavailable"));
    setSecret(null);
    setQr(null);
    onSignedOut();
  }

  if (step === "offer") {
    return (
      <section className="mt-6" aria-labelledby="totp-heading">
        <h2 id="totp-heading" className="text-lg font-semibold text-ledger-900">{t("account.totp.title")}</h2>
        <p className="text-sm text-slate-700">{t("account.totp.why")}</p>
        <button type="button" className={`${button} mt-2`} onClick={() => setStep("password")}>{t("account.totp.start")}</button>
      </section>
    );
  }

  return (
    <section className="mt-6 max-w-md rounded-md border border-slate-200 p-3" aria-labelledby="totp-heading">
      <h2 id="totp-heading" className="text-lg font-semibold text-ledger-900">{t("account.totp.title")}</h2>
      {error && <p role="alert" className="mt-2 text-sm text-red-800">{error}</p>}

      {step === "password" && (
        <form onSubmit={begin} className="mt-2">
          <label htmlFor="totp-pw" className="block text-sm font-medium text-ledger-900">{t("account.totp.passwordAgain")}</label>
          <input id="totp-pw" type="password" autoComplete="current-password" required className={input} value={password} onChange={(e) => setPassword(e.target.value)} />
          <div className="mt-3 flex gap-2">
            <button type="submit" className={button} disabled={busy || !password}>{t("account.totp.next")}</button>
            <button type="button" className={button} onClick={() => { setStep("offer"); setPassword(""); setError(null); }}>{t("account.totp.cancel")}</button>
          </div>
        </form>
      )}

      {step === "scan" && secret && (
        <form onSubmit={finish} className="mt-2">
          <p className="text-sm text-slate-700">{t("account.totp.scan")}</p>
          {/* eslint-disable-next-line @next/next/no-img-element -- a data: URL drawn in the browser; next/image has nothing to optimize */}
          {qr && <img src={qr} alt={t("account.totp.qrAlt")} width={192} height={192} className="mt-2" />}
          <p className="mt-2 text-sm text-slate-700">{t("account.totp.manual")}</p>
          <p className="mt-1 font-mono text-sm tracking-wider text-ledger-900" aria-label={t("account.totp.keyLabel")}>{groupKey(secret.key)}</p>
          <label htmlFor="totp-code" className="mt-3 block text-sm font-medium text-ledger-900">{t("account.totp.code")}</label>
          <input id="totp-code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required className={input} value={code} onChange={(e) => setCode(e.target.value)} />
          <label htmlFor="totp-pw2" className="mt-3 block text-sm font-medium text-ledger-900">{t("account.totp.passwordAgain")}</label>
          <input id="totp-pw2" type="password" autoComplete="current-password" required className={input} value={password} onChange={(e) => setPassword(e.target.value)} />
          <p className="mt-2 text-xs text-slate-500">{t("account.totp.signOutNote")}</p>
          <div className="mt-3 flex gap-2">
            <button type="submit" className={button} disabled={busy || !password || code.trim().length !== 6}>{t("account.totp.turnOn")}</button>
            <button type="button" className={button} onClick={() => { setStep("offer"); setSecret(null); setQr(null); setPassword(""); setCode(""); setError(null); }}>{t("account.totp.cancel")}</button>
          </div>
        </form>
      )}
    </section>
  );
}
