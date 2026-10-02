import type { DemographicMetric, DemographicOverlay } from "@/lib/types";

/** Census ACS / BLS figures for the area tied to this bill, per badge.
 *  Context, not an effect: the numbers describe a place, not what the bill
 *  does to it. A state bill has no geography of its own, so its numbers are
 *  for the primary sponsor's district -- said plainly, so nobody reads them
 *  as the bill's reach. ACS margins of error are always shown (BRD 7).
 *  Server-rendered, no interactivity. */

const SOURCE: Record<string, string> = {
  acs: "U.S. Census Bureau, American Community Survey 5-year estimates",
  bls: "U.S. Bureau of Labor Statistics, Local Area Unemployment Statistics",
};

function amount(value: number, unit: string): string {
  if (unit === "percent") return `${value.toLocaleString("en-US", { maximumFractionDigits: 1 })}%`;
  return `${value.toLocaleString("en-US", { maximumFractionDigits: 0 })} ${unit}`;
}

function margin(value: number, unit: string): string {
  const n = value.toLocaleString("en-US", { maximumFractionDigits: unit === "percent" ? 1 : 0 });
  return unit === "percent" ? `${n} points` : n;
}

function Metric({ m, source }: { m: DemographicMetric; source: string }) {
  if (m.estimate === null) {
    return (
      <li>
        {m.label}: <span className="text-slate-500">not available</span>
      </li>
    );
  }
  return (
    <li>
      {m.label}: <span className="font-medium text-ledger-900">{amount(m.estimate, m.unit)}</span>
      {m.margin_of_error !== null ? (
        <span className="text-slate-500"> (± {margin(m.margin_of_error, m.unit)} margin of error)</span>
      ) : source === "acs" ? (
        <span className="text-slate-500"> (margin of error not published)</span>
      ) : null}
    </li>
  );
}

function where(o: DemographicOverlay): string {
  return o.geography_type === "district"
    ? `${o.geography_id}, the primary sponsor's district`
    : `${o.geography_id} County`;
}

export default function AreaContext({ overlays }: { overlays: DemographicOverlay[] }) {
  if (overlays.length === 0) return null;
  const sponsorDistrict = overlays.some((o) => o.geography_type === "district");
  return (
    <section aria-labelledby="area-context" className="mt-5">
      <h2 id="area-context" className="text-sm font-semibold text-ledger-900">Area context</h2>
      <p className="text-xs text-slate-500">
        Background figures for the area, by topic. They describe the place, not what this bill would change.
        {sponsorDistrict &&
          " A state bill applies statewide; these figures cover only the primary sponsor's district."}
      </p>
      <div className="mt-2 space-y-2">
        {overlays.map((o) => (
          <div key={`${o.badge_slug}-${o.source}-${o.geography_id}`} className="rounded border border-slate-200 p-3 text-sm text-slate-700">
            <h3 className="text-xs font-medium text-slate-600">
              {o.badge_label} · {where(o)}
            </h3>
            <ul className="mt-1 space-y-0.5">
              {o.metrics.map((m) => (
                <Metric key={m.label} m={m} source={o.source} />
              ))}
            </ul>
            <p className="mt-1 text-[11px] text-slate-500">
              Source: {SOURCE[o.source] ?? o.source}, {o.as_of}.
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
