import Link from "next/link";

import { SECURITY_POLICY_URL, SECURITY_REPORT_URL } from "@/lib/links";

export const metadata = {
  title: "Privacy & Terms — Sunshine Ledger",
};

export default function PrivacyPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold text-ledger-900">Privacy &amp; Terms</h1>
      <p className="text-sm text-slate-500">Last updated September 2026.</p>

      <p className="mt-6 text-sm leading-relaxed text-slate-700">
        Sunshine Ledger is a Bernal Labs project that tracks Florida state and local
        legislation and summarizes it in plain language. This page explains what
        happens with your data when you use the site. It&apos;s written in plain language
        on purpose — Sunshine Ledger doesn&apos;t have a legal team, and this page hasn&apos;t
        been reviewed by a lawyer. If something here matters to you, read it critically
        rather than taking it as a binding legal guarantee.
      </p>

      <h2 className="mt-8 text-lg font-semibold text-ledger-900">What we don&apos;t do</h2>
      <ul className="mt-2 space-y-1 text-sm text-slate-700">
        <li>No accounts, no login, no passwords.</li>
        <li>No advertising, no ad trackers, no analytics-for-profit.</li>
        <li>No selling or sharing of any data with third parties for marketing.</li>
        <li>No payment processing — the site is free and has no monetization.</li>
      </ul>

      <h2 className="mt-8 text-lg font-semibold text-ledger-900">What data is collected</h2>

      <h3 className="mt-4 font-semibold text-slate-800">Location-based homepage default</h3>
      <p className="mt-1 text-sm leading-relaxed text-slate-700">
        On your first visit, the site makes a best-effort guess at your state/city
        (Florida vs. elsewhere; Miami/Jacksonville vs. elsewhere) so the homepage can
        default to locally relevant bills. This works by sending your IP address to a
        third-party lookup service (ip-api.com) for a one-time location lookup — your
        IP address is not stored in our database. You can always view every
        jurisdiction regardless of what was detected, using the dropdown on the browse
        page.
      </p>

      <h3 className="mt-4 font-semibold text-slate-800">Cookies</h3>
      <p className="mt-1 text-sm leading-relaxed text-slate-700">
        One cookie (<code>sl_geo_resolved</code>) is set for 24 hours to remember that
        the location check above already ran, so you aren&apos;t redirected back to your
        detected location if you&apos;ve manually chosen a different one. It doesn&apos;t track
        you across sites and isn&apos;t used for advertising.
      </p>

      <h3 className="mt-4 font-semibold text-slate-800">Browser storage and analytics</h3>
      <p className="mt-1 text-sm leading-relaxed text-slate-700">
        That cookie is the only thing the site stores in your browser. It doesn&apos;t use
        local storage, doesn&apos;t load any analytics or tracking scripts, and doesn&apos;t
        count or profile visitors.
      </p>

      <h3 className="mt-4 font-semibold text-slate-800">Map tiles</h3>
      <p className="mt-1 text-sm leading-relaxed text-slate-700">
        The <Link href="/map" className="underline hover:text-slate-900">map page</Link> loads
        its background map images directly from OpenStreetMap&apos;s servers, so your browser
        sends them your IP address, as it would to any website. Their handling of it is
        covered by the{" "}
        <a
          href="https://osmfoundation.org/wiki/Privacy_Policy"
          className="underline hover:text-slate-900"
        >
          OpenStreetMap Foundation privacy policy
        </a>
        . No other page loads anything from a third party.
      </p>

      <h3 className="mt-4 font-semibold text-slate-800">&quot;Flag this&quot; reports</h3>
      <p className="mt-1 text-sm leading-relaxed text-slate-700">
        If you report a suspected inaccuracy, the report text and (only if you choose
        to provide one) your email address are stored so the report can be reviewed.
        Providing an email is optional and only used to follow up on that specific
        report — it isn&apos;t used for marketing and isn&apos;t shown publicly anywhere on the
        site. The email is kept while the report is open, and deleted automatically
        within 90 days after the report is resolved. The report text itself is kept as
        part of the site&apos;s correction history.
      </p>

      <h3 className="mt-4 font-semibold text-slate-800">Standard server logs</h3>
      <p className="mt-1 text-sm leading-relaxed text-slate-700">
        Like most web services, our infrastructure (including Cloudflare, which sits in
        front of the site) keeps short-lived operational logs of requests, including IP
        address, for security and abuse-prevention purposes (e.g. rate-limiting
        automated abuse). These aren&apos;t used to build a profile of you and aren&apos;t
        retained long-term in our own systems.
      </p>

      <h2 className="mt-8 text-lg font-semibold text-ledger-900">The bill data itself</h2>
      <p className="mt-1 text-sm leading-relaxed text-slate-700">
        Bill text, status, sponsor names, and related information are drawn from public
        government sources (LegiScan, Legistar, and city legislative systems) and
        summarized with the help of an AI model. Every summary links to the source it
        was drawn from — click &quot;Sources&quot; on any bill to see where the underlying facts
        came from. Summaries are AI-generated and may occasionally be imprecise; if you
        see something that looks wrong, please use the &quot;Flag this&quot; link so it can be
        reviewed.
      </p>

      <h2 className="mt-8 text-lg font-semibold text-ledger-900">Terms of use</h2>
      <ul className="mt-2 space-y-1 text-sm leading-relaxed text-slate-700">
        <li>
          <span className="font-medium">Informational only, not legal advice.</span> Nothing on
          this site is legal advice or an official record. For anything that matters — a legal
          question, a vote, a compliance decision — rely on the official source, which every
          bill links to.
        </li>
        <li>
          <span className="font-medium">No guarantee of accuracy.</span> The site is provided
          as-is. Summaries are AI-generated, bill data can lag behind the official record, and
          coverage is partial. See{" "}
          <Link href="/methodology" className="underline hover:text-slate-900">
            how this works
          </Link>{" "}
          for the known limits.
        </li>
        <li>
          <span className="font-medium">Corrections.</span> Use &quot;Flag this&quot; on any bill.
          Reports go to manual review, and corrections are made against the original source.
        </li>
        <li>
          <span className="font-medium">Reusing the content.</span> The underlying bill records
          are public government records. If you quote a summary, please link back to the bill
          page so readers can see the source.
        </li>
      </ul>

      <h2 className="mt-8 text-lg font-semibold text-ledger-900">Security</h2>
      <p className="mt-1 text-sm leading-relaxed text-slate-700">
        Found a security problem? Please report it privately through{" "}
        <a href={SECURITY_REPORT_URL} className="underline hover:text-slate-900">
          GitHub&apos;s private vulnerability reporting
        </a>{" "}
        rather than a public issue. The{" "}
        <a href={SECURITY_POLICY_URL} className="underline hover:text-slate-900">
          security policy
        </a>{" "}
        covers what&apos;s in scope.
      </p>

      <h2 className="mt-8 text-lg font-semibold text-ledger-900">Contact</h2>
      <p className="mt-1 text-sm leading-relaxed text-slate-700">
        Questions about this page, or a request to delete the email on a report you
        submitted sooner, can be sent through the &quot;Flag this&quot; form on any bill, with
        your email included if you&apos;d like a reply.
      </p>
    </div>
  );
}
