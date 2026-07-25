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
}

export interface BillDetail extends BillListItem {
  last_action: string | null;
  full_text_url: string | null;
  sponsors: SponsorOut[];
  claims: ClaimOut[];
  news: NewsItemOut[];
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
