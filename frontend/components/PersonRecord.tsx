"use client";

import { useState, type ReactNode } from "react";

import SponsoredBills from "@/components/SponsoredBills";
import VotingRecord from "@/components/VotingRecord";
import { ALL_TOPICS, topicsVotedOn } from "@/lib/votingRecord";
import type { PersonBillItem, PersonVoteItem } from "@/lib/types";

/** The legislator page's voting record and sponsored bills, sharing one
 *  topic slicer. `children` (notes about missing votes) sits between them. */
export default function PersonRecord({
  votes,
  bills,
  children,
}: {
  votes: PersonVoteItem[];
  bills: PersonBillItem[];
  children?: ReactNode;
}) {
  const [topic, setTopic] = useState(ALL_TOPICS);
  const topicLabel = topicsVotedOn(votes).find((t) => t.slug === topic)?.label;

  return (
    <>
      {votes.length > 0 && <VotingRecord votes={votes} bills={bills} topic={topic} onTopic={setTopic} />}
      {children}
      <SponsoredBills bills={bills} topic={topic} topicLabel={topicLabel} />
    </>
  );
}
