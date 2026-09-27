"use client";

import { useState } from "react";
import Link from "next/link";

import {
  ALL_TOPICS,
  VOTE_KINDS,
  hasTopic,
  sponsorshipCounts,
  summarizeVotes,
  topicsVotedOn,
  type StageSummary,
} from "@/lib/votingRecord";
import type { PersonBillItem, PersonVoteItem } from "@/lib/types";

const PAGE = 25;

function StageLine({ label, summary }: { label: string; summary: StageSummary }) {
  return (
    <p className="text-sm text-slate-700">
      <span className="font-medium">{label}: </span>
      {summary.rollCalls === 0 ? (
        <span className="text-slate-500">none in the covered roll calls</span>
      ) : (
        <>
          {summary.rollCalls} roll call{summary.rollCalls === 1 ? "" : "s"} on {summary.bills} bill
          {summary.bills === 1 ? "" : "s"} —{" "}
          {VOTE_KINDS.map((k, i) => (
            <span key={k.value}>
              {i > 0 && " · "}
              {k.label} {summary.byVote[k.value] ?? 0}
            </span>
          ))}
        </>
      )}
    </p>
  );
}

/** A legislator's recorded votes, filterable by bill topic. Plain facts from
 *  official roll calls: counts and the votes themselves, no score, no
 *  percentages, no "for/against" framing, and no reasons -- a topic filter
 *  only says which bills the votes were on. */
export default function VotingRecord({ votes, bills }: { votes: PersonVoteItem[]; bills: PersonBillItem[] }) {
  const [topic, setTopic] = useState(ALL_TOPICS);
  const [shown, setShown] = useState(PAGE);
  const topics = topicsVotedOn(votes);
  const label = topics.find((t) => t.slug === topic)?.label;
  const matching = votes.filter((v) => hasTopic(v, topic));
  const { floor, committee } = summarizeVotes(votes, topic);
  const sponsorship = sponsorshipCounts(bills, topic);

  const choose = (slug: string) => {
    setTopic(slug);
    setShown(PAGE);
  };

  return (
    <section className="mt-4" aria-labelledby="voting-record-heading">
      <h2 id="voting-record-heading" className="text-sm font-semibold text-ledger-900">
        Voting record
      </h2>
      <p className="text-[11px] text-slate-500">
        Roll calls recorded by the Florida Legislature in the 2026 Regular and special sessions, via LegiScan.
        Voice votes aren&apos;t recorded. Plain counts, not a score or a claim about this legislator.
      </p>

      <div className="mt-2 flex flex-wrap gap-1.5" role="group" aria-label="Filter votes by bill topic">
        {[{ slug: ALL_TOPICS, label: "All topics", count: votes.length }, ...topics].map((t) => (
          <button
            key={t.slug || "all"}
            type="button"
            onClick={() => choose(t.slug)}
            aria-pressed={topic === t.slug}
            className={`rounded-full border px-2.5 py-0.5 text-xs ${
              topic === t.slug
                ? "border-ledger-900 bg-ledger-900 text-white"
                : "border-slate-300 text-slate-700 hover:border-slate-500"
            }`}
          >
            {t.label} {t.count}
          </button>
        ))}
      </div>

      <div className="mt-3 space-y-1 rounded-md bg-slate-50 p-3">
        <p className="text-sm font-medium text-ledger-900">
          {label ? `Recorded votes on bills tagged ${label}` : "All recorded votes"}
        </p>
        <StageLine label="Floor votes" summary={floor} />
        <StageLine label="Committee votes" summary={committee} />
        <p className="text-sm text-slate-700">
          <span className="font-medium">Sponsorship: </span>
          sponsored {sponsorship.sponsored} · co-sponsored {sponsorship.cosponsored} bill
          {sponsorship.cosponsored === 1 ? "" : "s"}
          {label ? ` tagged ${label}` : ""}
        </p>
        {label && (
          <p className="text-[11px] text-slate-500">
            A bill can carry several topics, so totals across topics overlap.
          </p>
        )}
      </div>

      <ul className="mt-2 space-y-1 text-sm">
        {matching.slice(0, shown).map((v, i) => (
          <li key={`${v.roll_call_id ?? v.entity_id}-${i}`} className="flex flex-wrap items-baseline justify-between gap-x-2">
            <span>
              <Link href={`/bills/${v.entity_id}`} className="text-sunshine-700 underline">
                {v.bill_number}
              </Link>
              <span className="text-slate-600"> {v.bill_name}</span>
              {v.roll_call_description && (
                <span className="block text-xs text-slate-500">
                  {v.stage === "floor" ? "Floor · " : ""}
                  {v.roll_call_description}
                  {v.source_url && (
                    <>
                      {" · "}
                      <a href={v.source_url} target="_blank" rel="noreferrer" className="underline">
                        roll call ↗
                      </a>
                    </>
                  )}
                </span>
              )}
            </span>
            <span className="shrink-0 text-xs text-slate-600">
              <span className="font-medium">{VOTE_KINDS.find((k) => k.value === v.vote)?.label ?? v.vote}</span>
              {v.date && <span className="text-slate-500"> · {v.date}</span>}
            </span>
          </li>
        ))}
      </ul>
      {matching.length > shown && (
        <button
          type="button"
          onClick={() => setShown(shown + PAGE)}
          className="mt-2 text-xs font-medium text-sunshine-700 underline hover:text-sunshine-800"
        >
          Show more ({matching.length - shown} more)
        </button>
      )}
    </section>
  );
}
