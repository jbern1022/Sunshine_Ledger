"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { BILL_READ_MS, USAGE_COUNTS_ENABLED, isOfficialSource, pageKindFor, sendUsage } from "@/lib/usage";

/** Counts page views, bill reads and clicks to official sources as daily
 *  totals (docs/USAGE_COUNTS_DESIGN.md). Renders nothing; does nothing at
 *  all unless NEXT_PUBLIC_USAGE_COUNTS_ENABLED is "true". */
export default function UsageBeacon() {
  const pathname = usePathname() || "/";

  useEffect(() => {
    if (!USAGE_COUNTS_ENABLED) return;
    const kind = pageKindFor(pathname);
    sendUsage("page_view", kind);
    if (kind !== "bill") return;

    // A read is 15 seconds of the page actually being visible, not 15 seconds open in a background tab.
    let visibleMs = 0;
    let since = document.visibilityState === "visible" ? Date.now() : null;
    let sent = false;
    const tick = () => {
      if (sent) return;
      const now = Date.now();
      if (since !== null) visibleMs += now - since;
      since = document.visibilityState === "visible" ? now : null;
      if (visibleMs >= BILL_READ_MS) {
        sent = true;
        sendUsage("bill_read", "bill");
      }
    };
    const timer = window.setInterval(tick, 1000);
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [pathname]);

  useEffect(() => {
    if (!USAGE_COUNTS_ENABLED) return;
    const onClick = (e: MouseEvent) => {
      const link = (e.target as Element | null)?.closest?.("a[href]") as HTMLAnchorElement | null;
      if (link && isOfficialSource(link.href)) sendUsage("source_click", pageKindFor(pathname));
    };
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, [pathname]);

  return null;
}
