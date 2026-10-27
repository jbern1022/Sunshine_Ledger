import type { Metadata } from "next";
import Link from "next/link";
import { DEFAULT_LOCALE, t } from "@/lib/i18n";
import { SECURITY_POLICY_URL } from "@/lib/links";
import "./globals.css";

export const metadata: Metadata = {
  title: t("site.title"),
  description: t("site.description"),
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang={DEFAULT_LOCALE}>
      <body>
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4">
            <Link href="/" className="flex items-center gap-2">
              <span className="text-xl font-bold text-ledger-900">{t("brand.name")}</span>
              <span className="rounded bg-sunshine-100 px-2 py-0.5 text-xs font-medium text-sunshine-700">
                {t("brand.badge")}
              </span>
            </Link>
            <nav className="flex gap-4 text-sm font-medium text-slate-600">
              <Link href="/" className="hover:text-ledger-900">
                {t("nav.browse")}
              </Link>
              <Link href="/people" className="hover:text-ledger-900">
                {t("nav.sponsors")}
              </Link>
              <Link href="/map" className="hover:text-ledger-900">
                {t("nav.map")}
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
        <footer className="mx-auto max-w-5xl px-4 py-8 text-xs text-slate-500">
          {t("footer.about")}{" "}
          <Link href="/methodology" className="underline hover:text-slate-600">{t("footer.how")}</Link> &middot; <Link href="/corrections" className="underline hover:text-slate-600">{t("footer.corrections")}</Link> &middot; <a href="/feed.xml" className="underline hover:text-slate-600">{t("footer.rss")}</a> &middot; <Link href="/privacy" className="underline hover:text-slate-600">{t("footer.privacy")}</Link> &middot; <a href={SECURITY_POLICY_URL} className="underline hover:text-slate-600">{t("footer.security")}</a>
        </footer>
      </body>
    </html>
  );
}
