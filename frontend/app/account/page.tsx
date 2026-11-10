import type { Metadata } from "next";
import { notFound } from "next/navigation";

import AccountPanel from "@/components/AccountPanel";
import { ACCOUNTS_ENABLED } from "@/lib/account";

export const metadata: Metadata = { title: "Your account — Sunshine Ledger", robots: { index: false } };

/** Reader accounts are built but off: with NEXT_PUBLIC_AUTH_ENABLED unset this page is a 404. */
export default function AccountPage() {
  if (!ACCOUNTS_ENABLED) notFound();
  return <AccountPanel />;
}
