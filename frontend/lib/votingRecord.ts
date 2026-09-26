import type { BillTopic, PersonBillItem, PersonVoteItem } from "./types";

export const ALL_TOPICS = "";

/** LegiScan's vote values, in the order they're shown. */
export const VOTE_KINDS = [
  { value: "Yea", label: "Yes" },
  { value: "Nay", label: "No" },
  { value: "NV", label: "Not voting" },
  { value: "Absent", label: "Absent" },
] as const;

export interface StageSummary {
  rollCalls: number;
  bills: number;
  byVote: Record<string, number>;
}

/** Topics this person has recorded votes on, with a roll-call count each,
 *  most frequent first. A bill can carry several topics, so these counts
 *  overlap and don't sum to the total. */
export function topicsVotedOn(votes: PersonVoteItem[]): (BillTopic & { count: number })[] {
  const counts = new Map<string, BillTopic & { count: number }>();
  for (const v of votes) {
    for (const t of v.tags ?? []) {
      const entry = counts.get(t.slug) ?? { ...t, count: 0 };
      entry.count += 1;
      counts.set(t.slug, entry);
    }
  }
  return [...counts.values()].sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}

export function hasTopic(item: { tags?: BillTopic[] }, topic: string): boolean {
  return topic === ALL_TOPICS || (item.tags ?? []).some((t) => t.slug === topic);
}

function summarize(votes: PersonVoteItem[]): StageSummary {
  const byVote: Record<string, number> = {};
  for (const v of votes) byVote[v.vote] = (byVote[v.vote] ?? 0) + 1;
  return { rollCalls: votes.length, bills: new Set(votes.map((v) => v.entity_id)).size, byVote };
}

/** Yes/No/Not voting/Absent counts, split into floor and committee votes,
 *  for the votes on bills with `topic`. Plain counts: no percentages, since
 *  the full set of roll calls someone could have voted in isn't known. */
export function summarizeVotes(
  votes: PersonVoteItem[],
  topic: string,
): { floor: StageSummary; committee: StageSummary } {
  const matching = votes.filter((v) => hasTopic(v, topic));
  return {
    floor: summarize(matching.filter((v) => v.stage === "floor")),
    committee: summarize(matching.filter((v) => v.stage !== "floor")),
  };
}

/** Distinct bills sponsored and co-sponsored, for bills with `topic`. A
 *  person listed as both on one bill counts once, as sponsor. */
export function sponsorshipCounts(bills: PersonBillItem[], topic: string): { sponsored: number; cosponsored: number } {
  const sponsored = new Set<string>();
  const cosponsored = new Set<string>();
  for (const b of bills.filter((b) => hasTopic(b, topic))) {
    (b.relationship_type === "sponsor" ? sponsored : cosponsored).add(b.entity_id);
  }
  for (const id of sponsored) cosponsored.delete(id);
  return { sponsored: sponsored.size, cosponsored: cosponsored.size };
}
