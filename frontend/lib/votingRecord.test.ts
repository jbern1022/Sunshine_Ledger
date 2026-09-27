import { describe, it, expect } from "vitest";
import { sponsorshipCounts, summarizeVotes, topicsVotedOn, ALL_TOPICS } from "./votingRecord";
import type { PersonBillItem, PersonVoteItem } from "./types";

const housing = { slug: "housing", label: "Housing" };
const taxes = { slug: "taxes_budget", label: "Taxes/Budget" };

const vote = (bill: string, v: string, stage: string, tags = [housing]): PersonVoteItem => ({
  entity_id: bill,
  bill_number: bill,
  bill_name: bill,
  vote: v,
  roll_call_description: stage === "floor" ? "House: Third Reading RCS#1" : "House Commerce Committee",
  date: "2026-03-04",
  stage,
  tags,
});

const votes = [
  vote("HB1", "Yea", "committee"),
  vote("HB1", "Nay", "floor"), // same bill, different roll call and vote
  vote("HB2", "Absent", "floor", [housing, taxes]),
  vote("HB3", "NV", "committee", [taxes]),
];

describe("voting record counts", () => {
  it("lists topics by roll-call count; a multi-topic bill counts under each", () => {
    expect(topicsVotedOn(votes).map((t) => [t.slug, t.count])).toEqual([
      ["housing", 3],
      ["taxes_budget", 2],
    ]);
  });

  it("splits floor and committee votes and counts roll calls and distinct bills", () => {
    const { floor, committee } = summarizeVotes(votes, "housing");
    expect(floor).toEqual({ rollCalls: 2, bills: 2, byVote: { Nay: 1, Absent: 1 } });
    expect(committee).toEqual({ rollCalls: 1, bills: 1, byVote: { Yea: 1 } });
  });

  it("covers everything with no topic selected", () => {
    const { floor, committee } = summarizeVotes(votes, ALL_TOPICS);
    expect(floor.rollCalls + committee.rollCalls).toBe(4);
  });

  it("counts distinct sponsored bills, a bill listed twice counting once as sponsor", () => {
    const bill = (id: string, rel: string, tags = [housing]): PersonBillItem => ({
      entity_id: id, bill_number: id, name: id, status: "Passed", relationship_type: rel,
      last_action_date: null, what_it_does: null, tags,
    });
    const bills = [bill("HB1", "sponsor"), bill("HB1", "co_sponsor"), bill("HB2", "co_sponsor"), bill("HB3", "sponsor", [taxes])];
    expect(sponsorshipCounts(bills, "housing")).toEqual({ sponsored: 1, cosponsored: 1 });
    expect(sponsorshipCounts(bills, ALL_TOPICS)).toEqual({ sponsored: 2, cosponsored: 1 });
  });
});
