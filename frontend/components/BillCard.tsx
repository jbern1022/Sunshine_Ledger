"use client";

import { useState } from "react";
import Link from "next/link";
import { fetchBill, submitFlag } from "@/lib/api";
import type { BillDetail, BillListItem, SourceOut } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  Introduced: "bg-slate-100 text-slate-700",
  "In Committee": "bg-amber-100 text-amber-800",
  "First Reading": "bg-amber-100 text-amber-800",
  "Passed Committee": "bg-blue-100 text-blue-800",
  Adopted: "bg-emerald-100 text-emerald-800",
  Passed: "bg-emerald-100 text-emerald-800",
};

function statusClass(status: string): string {
  return STATUS_COLORS[status] ?? "bg-slate-100 text-slate-700";
}

type FlagStatus = "idle" | "submitting" | "sent" | "error";

export default function BillCard({ bill }: { bill: BillListItem }) {
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<BillDetail | null>(null);

  const [showFlagForm, setShowFlagForm] = useState(false);
  const [flagReason, setFlagReason] = useState("");
  const [flagEmail, setFlagEmail] = useState("");
  const [flagStatus, setFlagStatus] = useState<FlagStatus>("idle");

  async function toggleExpanded() {
    if (!expanded && detail === null) {
      setLoading(true);
      try {
        setDetail(await fetchBill(bill.entity_id));
      } catch {
        setDetail(null);
      } finally {
        setLoading(false);
      }
    }
    setExpanded((v) => !v);
  }

  async function handleFlagSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFlagStatus("submitting");
    try {
      await submitFlag({
        bill_entity_id: bill.entity_id,
        reason_text: flagReason,
        reporter_email: flagEmail || null,
      });
      setFlagStatus("sent");
      setFlagReason("");
      setFlagEmail("");
    } catch {
      setFlagStatus("error");
    }
  }

  const uniqueSources: SourceOut[] = detail
    ? Array.from(new Map(detail.claims.flatMap((c) => c.sources).map((s) => [s.id, s])).values())
    : [];
  const whoItAffects = detail?.claims.find((c) => c.claim_type === "who_it_affects")?.claim_text ?? null;

  // Which model wrote the summaries on this card. Stored per claim, so the
  // fields can legitimately differ once cheaper-model routing is enabled
  // (see docs/LLM_MODEL_ROUTING.md) -- hence a set rather than one value.
  const summaryModels = Array.from(
    new Set(
      (detail?.claims ?? [])
        .filter((c) => c.generated_by.startsWith("llm:"))
        .map((c) => c.generated_by.slice("llm:".length)),
    ),
  );

  return (
    <article className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
            <span>{bill.bill_number}</span>
            <span>·</span>
            <span>{bill.jurisdiction_name ?? "Florida"}</span>
            {bill.chamber && (
              <>
                <span>·</span>
                <span>{bill.chamber}</span>
              </>
            )}
          </div>
          {/* Render the bill number verbatim. This used to strip a
              " (DEMO)" suffix, which meant seeded sample bills displayed
              under a heading indistinguishable from real legislation --
              the marker survived only in small metadata. If placeholder
              data ever reaches this component again it should be
              conspicuous, not tidied away. */}
          <h2 className="mt-1 text-lg font-semibold text-ledger-900">
            <Link href={`/bills/${bill.entity_id}`} className="hover:text-sunshine-600 hover:underline">
              {bill.bill_number}
            </Link>
          </h2>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-medium ${statusClass(bill.status)}`}>{bill.status}</span>
      </div>

      {bill.what_it_does ? (
        <p className="mt-3 text-sm leading-relaxed text-slate-700">{bill.what_it_does}</p>
      ) : (
        <p className="mt-3 text-sm italic text-slate-400">
          No plain-language summary generated yet.
          {bill.full_text_url && (
            <>
              {" "}
              <a
                href={bill.full_text_url}
                target="_blank"
                rel="noreferrer"
                className="not-italic text-sunshine-600 underline hover:text-sunshine-500"
              >
                Read the original bill text
              </a>
              .
            </>
          )}
        </p>
      )}

      <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-400">
        {bill.primary_sponsor && <span>Sponsored by {bill.primary_sponsor}</span>}
        {bill.geo_scope_names.length > 0 && (
          <span>
            {bill.geo_scope_type} — {bill.geo_scope_names.join(", ")}
          </span>
        )}
        {bill.full_text_url && (
          <a
            href={bill.full_text_url}
            target="_blank"
            rel="noreferrer"
            className="text-sunshine-600 underline hover:text-sunshine-500"
          >
            View original bill ↗
          </a>
        )}
      </p>

      <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3">
        <div className="flex items-center gap-4">
          <button
            onClick={toggleExpanded}
            className="flex items-center gap-1.5 text-xs font-medium text-sunshine-600 hover:text-sunshine-500"
          >
            <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-sunshine-100 px-1.5 text-[10px] font-bold text-sunshine-600">
              {bill.source_count}
            </span>
            {expanded ? "Hide sources" : `Sources (${bill.source_count})`}
          </button>
          <button
            onClick={() => setShowFlagForm((v) => !v)}
            className="text-xs font-medium text-slate-400 hover:text-slate-600"
          >
            Flag this
          </button>
        </div>
        <span className="text-xs text-slate-400">
          {bill.last_action_date ? `Last action ${bill.last_action_date}` : ""}
        </span>
      </div>

      {expanded && (
        <div className="mt-3 rounded-md bg-slate-50 p-3 text-xs">
          {loading && <p className="text-slate-400">Loading sources…</p>}
          {!loading && whoItAffects && (
            <p className="mb-2 text-slate-600">
              <span className="font-semibold">Who it affects: </span>
              {whoItAffects}
            </p>
          )}
          {!loading && detail && detail.sponsors.length > 0 && (
            <p className="mb-2 text-slate-600">
              <span className="font-semibold">Sponsors: </span>
              {detail.sponsors
                .map((s) => (s.relationship_type === "co_sponsor" ? `${s.name} (co-sponsor)` : s.name))
                .join(", ")}
            </p>
          )}
          {!loading && uniqueSources.length > 0 && (
            <ul className="space-y-1">
              {uniqueSources.map((s) => (
                <li key={s.id}>
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sunshine-600 underline hover:text-sunshine-500"
                  >
                    {s.publisher ?? s.url}
                  </a>
                  <span className="text-slate-400"> — retrieved {new Date(s.retrieved_at).toLocaleDateString()}</span>
                </li>
              ))}
            </ul>
          )}
          {/* Disclose authorship where the summary is actually read. The
              privacy page already said summaries are AI-generated, but
              nobody reading a bill card sees that. On a site whose premise
              is that claims are traceable, how the text was produced is
              part of what needs tracing. */}
          {!loading && summaryModels.length > 0 && (
            <p className="mt-2 border-t border-slate-200 pt-2 text-[11px] leading-relaxed text-slate-400">
              Plain-language summaries above were written by an AI model (
              {summaryModels.join(", ")}) from the source{uniqueSources.length === 1 ? "" : "s"} listed
              here, and are published without a human reviewing each one. They can be wrong or
              incomplete — the linked source is the authority. Something look off?{" "}
              <button
                type="button"
                onClick={() => setShowFlagForm(true)}
                className="underline hover:text-slate-600"
              >
                Flag it
              </button>
              .
            </p>
          )}
          {!loading && detail && uniqueSources.length === 0 && (
            <p className="text-slate-400">
              No summary sources yet (no plain-language summary has been generated for this bill) — see
              &quot;View original bill&quot; above for where this data came from.
            </p>
          )}
        </div>
      )}

      {showFlagForm && (
        <div className="mt-3 rounded-md border border-slate-200 bg-slate-50 p-3">
          {flagStatus === "sent" ? (
            <p className="text-xs text-emerald-700">
              Thanks — this has been sent for manual review. We don&apos;t edit bill data automatically from reports.
            </p>
          ) : (
            <form onSubmit={handleFlagSubmit} className="space-y-2">
              <label className="block text-xs font-medium text-slate-600">
                What looks wrong?
                <textarea
                  required
                  minLength={5}
                  maxLength={2000}
                  value={flagReason}
                  onChange={(e) => setFlagReason(e.target.value)}
                  rows={3}
                  className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-xs focus:border-sunshine-500 focus:outline-none focus:ring-1 focus:ring-sunshine-500"
                  placeholder="e.g. the &quot;who it affects&quot; summary misses that this only applies to counties over 500,000 residents"
                />
              </label>
              <label className="block text-xs font-medium text-slate-600">
                Email (optional, if you want a reply)
                <input
                  type="email"
                  value={flagEmail}
                  onChange={(e) => setFlagEmail(e.target.value)}
                  className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-xs focus:border-sunshine-500 focus:outline-none focus:ring-1 focus:ring-sunshine-500"
                />
              </label>
              {flagStatus === "error" && <p className="text-xs text-red-600">Couldn&apos;t submit — try again.</p>}
              <div className="flex items-center gap-2">
                <button
                  type="submit"
                  disabled={flagStatus === "submitting"}
                  className="rounded-md bg-sunshine-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-sunshine-600 disabled:opacity-50"
                >
                  {flagStatus === "submitting" ? "Sending…" : "Submit report"}
                </button>
                <button
                  type="button"
                  onClick={() => setShowFlagForm(false)}
                  className="text-xs text-slate-400 hover:text-slate-600"
                >
                  Cancel
                </button>
              </div>
            </form>
          )}
        </div>
      )}

      {expanded && !loading && detail && detail.news.length > 0 && (
        <div className="mt-3 rounded-md bg-slate-50 p-3 text-xs">
          <p className="mb-1.5 font-semibold text-slate-600">Recent news mentions</p>
          <ul className="space-y-1">
            {detail.news.map((n) => (
              <li key={n.id}>
                <a href={n.url} target="_blank" rel="noreferrer" className="text-sunshine-600 underline hover:text-sunshine-500">
                  {n.title}
                </a>
                <span className="text-slate-400">
                  {" "}
                  — {n.publisher ?? "unknown outlet"}
                  {n.published_date ? `, ${new Date(n.published_date).toLocaleDateString()}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}
