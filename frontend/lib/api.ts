import type { BillDetail, BillListResponse, CountyFeatureCollection, FlagCreate } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface BillSearchParams {
  q?: string;
  jurisdiction_name?: string;
  jurisdiction_level?: string;
  status?: string;
  limit?: number;
  offset?: number;
}

export async function fetchBills(params: BillSearchParams = {}): Promise<BillListResponse> {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") search.set(key, String(value));
  });

  const res = await fetch(`${API_URL}/bills?${search.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch bills: ${res.status}`);
  return res.json();
}

export async function fetchBill(entityId: string): Promise<BillDetail> {
  const res = await fetch(`${API_URL}/bills/${entityId}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch bill: ${res.status}`);
  return res.json();
}

export async function fetchCountyGeoJSON(): Promise<CountyFeatureCollection> {
  const res = await fetch(`${API_URL}/map/counties`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch map data: ${res.status}`);
  return res.json();
}

export async function submitFlag(payload: FlagCreate): Promise<void> {
  const res = await fetch(`${API_URL}/flags`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Failed to submit flag: ${res.status}`);
  }
}
