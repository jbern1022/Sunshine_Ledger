"use client";

import { useState } from "react";
import Link from "next/link";

import { t } from "@/lib/i18n";
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
      <span className="font-medium">{t("voting.stage.label", { label })}</span>
      {summary.rollCalls === 0 ? (
        <span className="text-slate-500">{t("voting.stage.none")}</span>
      ) : (
        <>
          {t("voting.stage.summary", {
            rollCalls: t("voting.stage.rollCalls", { count: summary.rollCalls }),
            bills: t("voting.stage.bills", { count: summary.bills }),
          })}
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
 *  only says which bills the votes were on. The topic lives in PersonRecord,
 *  which filters the sponsored bills by it too. The vote list starts
 *  collapsed (hundreds of rows for a long-serving member); the slicer and
 *  counts are always shown. */
export default function VotingRecord({
  votes,
  bills,
  topic,
  onTopic,
}: {
  votes: PersonVoteItem[];
  bills: PersonBillItem[];
  topic: string;
  onTopic: (slug: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [shown, setShown] = useState(PAGE);
  const topics = topicsVotedOn(votes);
  const label = topics.find((tp) => tp.slug === topic)?.label;
  const matching = votes.filter((v) => hasTopic(v, topic));
  const { floor, committee } = summarizeVotes(votes, topic);
  const sponsorship = sponsorshipCounts(bills, topic);

  const choose = (slug: string) => {
    onTopic(slug);
    setShown(PAGE);
  };

  return (
    <section className="mt-4" aria-labelledby="voting-record-heading">
      <h2 id="voting-record-heading" className="text-sm font-semibold text-ledger-900">
        {t("voting.title")}
      </h2>
      <p className="text-[11px] text-slate-500">
        {t("voting.note")}
      </p>

      <div className="mt-2 flex flex-wrap gap-1.5" role="group" aria-label={t("voting.filter.label")}>
        {[{ slug: ALL_TOPICS, label: t("voting.allTopics"), count: votes.length }, ...topics].map((tp) => (
          <button
            key={tp.slug || "all"}
            type="button"
            onClick={() => choose(tp.slug)}
            aria-pressed={topic === tp.slug}
            className={`rounded-full border px-2.5 py-0.5 text-xs ${
              topic === tp.slug
                ? "border-ledger-900 bg-ledger-900 text-white"
                : "border-slate-300 text-slate-700 hover:border-slate-500"
            }`}
          >
            {t("voting.topicChip", { label: tp.label, count: String(tp.count) })}
          </button>
        ))}
      </div>

      <div className="mt-3 space-y-1 rounded-md bg-slate-50 p-3">
        <p className="text-sm font-medium text-ledger-900">
          {label ? t("voting.heading.tagged", { topic: label }) : t("voting.heading.all")}
        </p>
        <StageLine label={t("voting.stage.floor")} summary={floor} />
        <StageLine label={t("voting.stage.committee")} summary={committee} />
        <p className="text-sm text-slate-700">
          <span className="font-medium">{t("voting.sponsorship")}</span>
          {t("voting.sponsorship.counts", { sponsored: sponsorship.sponsored, count: sponsorship.cosponsored })}
          {label ? t("voting.sponsorship.tagged", { topic: label }) : ""}
        </p>
        {label && (
          <p className="text-[11px] text-slate-500">
            {t("voting.overlap")}
          </p>
        )}
      </div>

      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls="vote-list"
        className="mt-2 text-xs font-medium text-sunshine-700 underline hover:text-sunshine-800"
      >
        {open ? t("voting.hide") : t("voting.show", { count: matching.length })}
      </button>

      {open && (
        <ul id="vote-list" className="mt-2 space-y-1 text-sm">
          {matching.slice(0, shown).map((v, i) => (
            <li key={`${v.roll_call_id ?? v.entity_id}-${i}`} className="flex flex-wrap items-baseline justify-between gap-x-2">
              <span>
                <Link href={`/bills/${v.entity_id}`} className="text-sunshine-700 underline">
                  {v.bill_number}
                </Link>
                <span className="text-slate-600"> {v.bill_name}</span>
                {v.roll_call_description && (
                  <span className="block text-xs text-slate-500">
                    {v.stage === "floor" ? t("voting.floorPrefix") : ""}
                    {v.roll_call_description}
                    {v.source_url && (
                      <>
                        {" · "}
                        <a href={v.source_url} target="_blank" rel="noreferrer" className="underline">
                          {t("voting.rollCall")}
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
      )}
      {open && matching.length > shown && (
        <button
          type="button"
          onClick={() => setShown(shown + PAGE)}
          className="mt-2 text-xs font-medium text-sunshine-700 underline hover:text-sunshine-800"
        >
          {t("voting.more", { count: matching.length - shown })}
        </button>
      )}
    </section>
  );
}
