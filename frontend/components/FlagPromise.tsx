"use client";

import { useState } from "react";
import { flagPromise } from "@/lib/api";
import { t } from "@/lib/i18n";

/** 'Flag this statement' on a collected promise. Flagged items go to the top
 *  of the review queue. */
export default function FlagPromise({ id }: { id: string }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("sending");
    try {
      await flagPromise(id, reason);
      setStatus("sent");
    } catch {
      setStatus("error");
    }
  }

  if (status === "sent") return <p className="mt-2 text-xs text-emerald-700">{t("promises.flagSent")}</p>;

  return (
    <div className="mt-2">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="text-xs text-slate-600 underline hover:text-slate-900"
      >
        {t("promises.flag")}
      </button>
      {open && (
        <form onSubmit={submit} className="mt-2 space-y-2 rounded-md border border-slate-200 bg-slate-50 p-3">
          <label className="block text-xs font-medium text-slate-600">
            {t("promises.flagWhat")}
            <textarea
              required
              minLength={5}
              maxLength={2000}
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-xs"
            />
          </label>
          {status === "error" && <p className="text-xs text-red-600">{t("promises.flagError")}</p>}
          <button
            type="submit"
            disabled={status === "sending"}
            className="rounded-md bg-sunshine-500 px-3 py-1.5 text-xs font-medium text-ledger-900 hover:bg-sunshine-400 disabled:opacity-50"
          >
            {t("promises.flagSubmit")}
          </button>
        </form>
      )}
    </div>
  );
}
