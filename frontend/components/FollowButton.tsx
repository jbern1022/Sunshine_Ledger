"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ACCOUNTS_ENABLED, addWatch, getMe, getWatchlist, removeWatch, type WatchItem } from "@/lib/account";
import { t } from "@/lib/i18n";

/** Follow a bill, an official or a topic. Renders nothing unless accounts are switched on in this build.
 *  A visitor who is not signed in sees a link to sign in; following is free. */
export default function FollowButton({ kind, target, jurisdiction = "", label }: { kind: WatchItem["kind"]; target: string; jurisdiction?: string; label: string }) {
  const [state, setState] = useState<"loading" | "out" | "off" | "on">("loading");
  const [watchId, setWatchId] = useState<string | null>(null);
  const [problem, setProblem] = useState(false);

  useEffect(() => {
    if (!ACCOUNTS_ENABLED) return;
    let cancelled = false;
    (async () => {
      const me = await getMe();
      if (cancelled) return;
      if (!me || me.restricted) return setState("out");
      const items = await getWatchlist();
      if (cancelled) return;
      const hit = (items ?? []).find((w) => w.kind === kind && w.target === target && (w.jurisdiction ?? "") === jurisdiction);
      setWatchId(hit?.id ?? null);
      setState(hit ? "on" : "off");
    })();
    return () => {
      cancelled = true;
    };
  }, [kind, target, jurisdiction]);

  if (!ACCOUNTS_ENABLED || state === "loading") return null;
  if (state === "out") {
    return <Link href="/account" className="text-xs text-sunshine-700 underline">{t("follow.signIn", { what: label })}</Link>;
  }
  async function toggle() {
    setProblem(false);
    if (state === "on" && watchId) {
      if (await removeWatch(watchId)) { setState("off"); setWatchId(null); } else setProblem(true);
      return;
    }
    const r = await addWatch(kind, target, jurisdiction);
    if (!r.ok) return setProblem(true);
    const items = await getWatchlist();
    setWatchId((items ?? []).find((w) => w.kind === kind && w.target === target && (w.jurisdiction ?? "") === jurisdiction)?.id ?? null);
    setState("on");
  }
  return (
    <span>
      <button
        type="button"
        onClick={toggle}
        aria-pressed={state === "on"}
        className="rounded-md border border-sunshine-700 px-2.5 py-1 text-xs font-medium text-sunshine-700 hover:bg-sunshine-50"
      >
        {state === "on" ? t("follow.following", { what: label }) : t("follow.follow", { what: label })}
      </button>
      {problem && <span role="alert" className="ml-2 text-xs text-red-800">{t("follow.problem")}</span>}
    </span>
  );
}
