import type { Metadata } from "next";
import Link from "next/link";
import { SECURITY_POLICY_URL } from "@/lib/links";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sunshine Ledger",
  description: "Florida state and local legislation, in plain language, mapped by impact.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4">
            <Link href="/" className="flex items-center gap-2">
              <span className="text-xl font-bold text-ledger-900">Sunshine Ledger</span>
              <span className="rounded bg-sunshine-100 px-2 py-0.5 text-xs font-medium text-sunshine-600">
                FLORIDA · MVP
              </span>
            </Link>
            <nav className="flex gap-4 text-sm font-medium text-slate-600">
              <Link href="/" className="hover:text-ledger-900">
                Browse
              </Link>
              <Link href="/people" className="hover:text-ledger-900">
                Sponsors
              </Link>
              <Link href="/map" className="hover:text-ledger-900">
                Map
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
        <footer className="mx-auto max-w-5xl px-4 py-8 text-xs text-slate-400">
          Bernal Labs · Sunshine Ledger MVP. Bill data from LegiScan (Florida), Legistar (Jacksonville), and
          Granicus iQM2 (Miami). Every claim links to a source. Informational only, not legal advice.{" "}
          <Link href="/methodology" className="underline hover:text-slate-600">How this works</Link> &middot; <a href="/feed.xml" className="underline hover:text-slate-600">RSS</a> &middot; <Link href="/privacy" className="underline hover:text-slate-600">Privacy &amp; Terms</Link> &middot; <a href={SECURITY_POLICY_URL} className="underline hover:text-slate-600">Security</a>
        </footer>
      </body>
    </html>
  );
}
