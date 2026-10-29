"use client";

import { useState } from "react";
import { submitFlag } from "@/lib/api";
import { t } from "@/lib/i18n";
import type { ChallengeCategory, FlagCreate } from "@/lib/types";

/** Report that something on a bill page is wrong (the correction process:
 *  Notion spec, decisions agreed 2026-10-01). Optionally aimed at one block
 *  and version, so the review knows exactly what was challenged. */

type Target = Pick<FlagCreate, "object_type" | "object_id" | "object_version" | "claim_id">;

const CATEGORIES: ChallengeCategory[] = [
  "factually_wrong",
  "misleading",
  "wrong_source",
  "outdated",
  "wrong_entity",
  "other",
];

type Status = "idle" | "submitting" | "sent" | "error";

const field =
  "mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-xs focus:border-sunshine-500 focus:outline-none focus:ring-1 focus:ring-sunshine-500";

export default function ChallengeForm({
  billEntityId,
  target = {},
  onClose,
}: {
  billEntityId: string;
  target?: Target;
  onClose?: () => void;
}) {
  const [category, setCategory] = useState<ChallengeCategory>("factually_wrong");
  const [reason, setReason] = useState("");
  const [evidenceUrl, setEvidenceUrl] = useState("");
  const [evidenceText, setEvidenceText] = useState("");
  const [named, setNamed] = useState(false);
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<Status>("idle");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("submitting");
    try {
      await submitFlag({
        bill_entity_id: billEntityId,
        ...target,
        category,
        reason_text: reason,
        evidence_url: evidenceUrl || null,
        evidence_text: evidenceText || null,
        is_named_party: named,
        reporter_email: email || null,
      });
      setStatus("sent");
    } catch {
      setStatus("error");
    }
  }

  if (status === "sent") {
    return (
      <p className="mt-2 text-xs text-emerald-700">
        {t("challenge.sent")}
      </p>
    );
  }

  return (
    <form onSubmit={submit} className="mt-2 space-y-2 rounded-md border border-slate-200 bg-slate-50 p-3">
      <label className="block text-xs font-medium text-slate-600">
        {t("challenge.kind")}
        <select value={category} onChange={(e) => setCategory(e.target.value as ChallengeCategory)} className={field}>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {t(`challenge.category.${c}.label`)}
            </option>
          ))}
        </select>
      </label>
      <label className="block text-xs font-medium text-slate-600">
        {t("challenge.what")}
        <textarea
          required
          minLength={5}
          maxLength={2000}
          rows={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className={field}
          placeholder={t("challenge.whatPlaceholder")}
        />
      </label>
      <label className="block text-xs font-medium text-slate-600">
        {t("challenge.evidenceUrl")}
        <input type="url" value={evidenceUrl} onChange={(e) => setEvidenceUrl(e.target.value)} className={field} placeholder="https://" />
      </label>
      <label className="block text-xs font-medium text-slate-600">
        {t("challenge.evidenceText")}
        <textarea rows={2} maxLength={4000} value={evidenceText} onChange={(e) => setEvidenceText(e.target.value)} className={field} />
      </label>
      <label className="flex items-center gap-2 text-xs text-slate-600">
        <input type="checkbox" checked={named} onChange={(e) => setNamed(e.target.checked)} />
        {t("challenge.named")}
      </label>
      <label className="block text-xs font-medium text-slate-600">
        {t("challenge.email")}
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className={field} />
      </label>
      {status === "error" && <p className="text-xs text-red-600">{t("challenge.error")}</p>}
      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={status === "submitting"}
          className="rounded-md bg-sunshine-500 px-3 py-1.5 text-xs font-medium text-ledger-900 hover:bg-sunshine-400 disabled:opacity-50"
        >
          {status === "submitting" ? t("challenge.sending") : t("challenge.submit")}
        </button>
        {onClose && (
          <button type="button" onClick={onClose} className="text-xs text-slate-500 hover:text-slate-600">
            {t("challenge.cancel")}
          </button>
        )}
      </div>
    </form>
  );
}

/** "Flag this" link that opens the form in place. */
export function FlagThis({
  billEntityId,
  target,
  label = t("card.flag"),
}: {
  billEntityId: string;
  target?: Target;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="text-[11px] text-slate-500 underline hover:text-slate-700"
      >
        {label}
      </button>
      {open && <ChallengeForm billEntityId={billEntityId} target={target} onClose={() => setOpen(false)} />}
    </div>
  );
}
