// The one place layer and origin keys become display text. Components never
// derive a heading or badge from block position or content -- only from
// these keys -- so a block can't be rendered under the wrong label.
import type { BillLayers, LayerKey, LayerVersion, Origin } from "@/lib/types";

export const LAYER_ORDER: LayerKey[] = ["bill_says", "interpretation", "expected_effect"];

export const LAYER_META: Record<LayerKey, { title: string; definition: string }> = {
  bill_says: { title: "Bill Says", definition: "The bill's own words." },
  interpretation: { title: "Interpretation", definition: "What the change means." },
  expected_effect: {
    title: "Expected Effect",
    definition: "What may happen. Forecasts, not established facts, and not legal or financial advice.",
  },
};

export const ORIGINS_FOR_LAYER: Record<LayerKey, Origin[]> = {
  bill_says: ["bill_text"],
  interpretation: ["legislative_staff", "sunshine_ledger_ai"],
  expected_effect: ["legislative_staff", "sunshine_ledger_ai"],
};

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

export function originBadge(origin: Origin, version: LayerVersion | null): string {
  if (origin === "bill_text") return "Bill text";
  if (origin === "legislative_staff") {
    // scope_note is "Staff analysis, <committee>, <date>" for staff blocks.
    const detail = version?.scope_note.replace(/^Staff analysis, /, "").replace(/ has no .*$/, "").replace(/:.*$/, "");
    return detail ? `Legislative staff analysis · ${detail} · condensed by AI` : "Legislative staff analysis";
  }
  return "Sunshine Ledger analysis · AI-generated";
}

export function reviewLabel(origin: Origin, version: LayerVersion): string | null {
  if (origin === "bill_text") return null;
  if (version.review_status === "reviewed" && version.reviewed_at) {
    return `reviewed by a person on ${formatDate(version.reviewed_at)}`;
  }
  return "not reviewed by a person";
}

export function hasAnyLayer(layers: BillLayers | undefined): boolean {
  return !!layers && LAYER_ORDER.some((k) => layers[k].length > 0);
}
