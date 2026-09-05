export interface SourceOut {
  id: string;
  url: string;
  publisher: string | null;
  source_type: string;
  retrieved_at: string;
}

export interface ClaimOut {
  id: string;
  claim_type: "what_it_does" | "who_it_affects" | "status_update";
  claim_text: string;
  generated_by: string;
  source_count: number;
  sources: SourceOut[];
}

export interface SponsorOut {
  entity_id: string;
  name: string;
  relationship_type: string;
}

export interface BillListItem {
  entity_id: string;
  bill_number: string;
  /** The bill's actual title, distinct from its number. */
  name: string;
  session: string;
  chamber: string | null;
  status: string;
  jurisdiction_level: string | null;
  jurisdiction_name: string | null;
  geo_scope_type: string | null;
  geo_scope_names: string[];
  introduced_date: string | null;
  last_action_date: string | null;
  what_it_does: string | null;
  source_count: number;
  full_text_url: string | null;
  primary_sponsor: string | null;
}

export interface IndividualVoteOut {
  person_entity_id: string;
  person_name: string;
  vote: string;
}

/** A single roll-call vote. Plain facts only -- tallies and who voted which
 *  way, sourced from LegiScan. Not a score or a characterization of anyone. */
export interface RollCallOut {
  id: string;
  roll_call_id: string;
  chamber: string | null;
  description: string;
  date: string;
  yea: number | null;
  nay: number | null;
  nv: number | null;
  absent: number | null;
  total: number | null;
  passed: boolean;
  source_url: string | null;
  votes: IndividualVoteOut[];
}

export interface BillDetail extends BillListItem {
  last_action: string | null;
  sponsors: SponsorOut[];
  claims: ClaimOut[];
  news: NewsItemOut[];
  votes: RollCallOut[];
}

export interface BillListResponse {
  total: number;
  items: BillListItem[];
}

export interface CountyFeatureProperties {
  scope_type: string;
  scope_name: string;
  bill_count: number;
  source: string | null;
}

/** Sponsorship activity per legislative district — NOT geographic impact.
 *  `bill_count` is how many tracked bills that district's legislator filed.
 *  See the /map/districts docstring before reusing this anywhere. */
export interface DistrictFeatureProperties {
  scope_type: string;
  scope_name: string;
  chamber: string;
  bill_count: number;
  legislators: string[];
  source: string | null;
}

export interface NewsItemOut {
  id: string;
  title: string;
  url: string;
  publisher: string | null;
  published_date: string | null;
}

export interface FlagCreate {
  bill_entity_id: string;
  claim_id?: string | null;
  reason_text: string;
  reporter_email?: string | null;
}

export interface CountyFeatureCollection {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: unknown;
    properties: CountyFeatureProperties;
  }>;
}

export interface DistrictFeatureCollection {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: unknown;
    properties: DistrictFeatureProperties;
  }>;
}

/** Published election dates (BRD 5.8). Deliberately carries no candidate,
 *  party, or outcome data — the BRD permits the calendar but rules out
 *  scoring and predictive claims at MVP. */
export interface ElectionEvent {
  date: string;
  label: string;
  kind: string;
  is_past: boolean;
  days_away: number;
}

export interface ElectionCalendar {
  state: string;
  year: number;
  source: { name: string; url: string };
  verify_by: string;
  as_of: string;
  next_event: ElectionEvent | null;
  events: ElectionEvent[];
}

/** A legislator who sponsors tracked bills. Counts are plain facts drawn
 *  from bill records — deliberately not a ranking or an activity score. */
export interface PersonListItem {
  entity_id: string;
  name: string;
  district: string | null;
  role: string | null;
  party: string | null;
  jurisdiction_name: string | null;
  sponsored_count: number;
}

export interface PersonBillItem {
  entity_id: string;
  bill_number: string;
  name: string;
  status: string;
  relationship_type: string;
  last_action_date: string | null;
  what_it_does: string | null;
}

/** One roll-call vote this legislator cast. Plain fact only -- how they
 *  voted, not a score or a consistency judgement. */
export interface PersonVoteItem {
  entity_id: string;
  bill_number: string;
  bill_name: string;
  vote: string;
  roll_call_description: string | null;
  date: string | null;
}

export interface PersonDetail extends PersonListItem {
  bills: PersonBillItem[];
  votes: PersonVoteItem[];
}

export interface PersonListResponse {
  total: number;
  items: PersonListItem[];
}

/** A status and how many bills carry it. Options come from the data rather
 *  than a hardcoded list, because the three sources use different
 *  vocabularies and any fixed list would drift. */
export interface StatusCount {
  status: string;
  count: number;
}
