"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { MapContainer, TileLayer, GeoJSON } from "react-leaflet";
import type { Layer, PathOptions } from "leaflet";
import "leaflet/dist/leaflet.css";
import { t, tRich } from "@/lib/i18n";
import { fetchCountyGeoJSON, fetchDistrictGeoJSON } from "@/lib/api";
import type {
  CountyFeatureCollection,
  CountyFeatureProperties,
  DistrictFeatureCollection,
  DistrictFeatureProperties,
} from "@/lib/types";

const FL_CENTER: [number, number] = [27.8, -81.7];

/** The two views answer different questions and must not be conflated:
 *  "impact" shades by a bill's geographic scope, "sponsorship" shades by
 *  which district's legislator filed it. Nearly every state bill is
 *  statewide in effect, so a dark district never means "only this district
 *  is affected". The mode copy below carries that caveat -- keep it. */
type MapMode = "impact" | "sponsorship";

const MODE_KEYS: MapMode[] = ["impact", "sponsorship"];

function colorForImpact(count: number): string {
  if (count === 0) return "#e2e8f0"; // slate-200
  if (count === 1) return "#fde68a"; // amber-200
  if (count <= 3) return "#f5c518"; // sunshine-400
  return "#b58200"; // sunshine-600
}

/** Sponsorship counts run far higher than per-county impact counts (a single
 *  legislator files dozens of bills), so the impact thresholds would render
 *  nearly every district at max shade.
 *
 *  Breaks are the quartiles of the real FL distribution (n=160: median 25,
 *  p25 15, p75 38, max 109) rather than round numbers -- picking plausible
 *  round thresholds first put 55% of districts in the top bucket, which
 *  flattened the map into one colour. Re-check these if the corpus grows
 *  substantially or another state is added. */
function colorForSponsorship(count: number): string {
  if (count === 0) return "#e2e8f0";
  if (count <= 15) return "#fde68a";
  if (count <= 38) return "#f5c518";
  return "#b58200";
}

export default function MapView() {
  const router = useRouter();
  const [mode, setMode] = useState<MapMode>("impact");
  const [counties, setCounties] = useState<CountyFeatureCollection | null>(null);
  const [districts, setDistricts] = useState<DistrictFeatureCollection | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchCountyGeoJSON()
      .then(setCounties)
      .catch((err) => setError(err.message ?? t("map.error.county")));
  }, []);

  // Districts are fetched lazily -- the polygon set is much larger than the
  // county set, and most visitors never leave the default impact view.
  useEffect(() => {
    if (mode !== "sponsorship" || districts !== null) return;
    fetchDistrictGeoJSON()
      .then(setDistricts)
      .catch((err) => setError(err.message ?? t("map.error.district")));
  }, [mode, districts]);

  if (error) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        {tRich("map.error.hint", {
          error,
          loader: <code>python -m app.pipeline.load_boundaries</code>,
          seed: <code>seed.py</code>,
        })}
      </div>
    );
  }

  const active = mode === "impact" ? counties : districts;

  return (
    <div>
      <div className="mb-3">
        <div
          role="group"
          aria-label={t("map.viewLabel")}
          className="inline-flex rounded-md border border-slate-300 p-0.5"
        >
          {MODE_KEYS.map((key) => (
            <button
              key={key}
              onClick={() => setMode(key)}
              aria-pressed={mode === key}
              className={`rounded px-3 py-1.5 text-xs font-medium transition-colors ${
                mode === key
                  ? "bg-sunshine-500 text-ledger-900"
                  : "text-slate-600 hover:bg-slate-50"
              }`}
            >
              {t(`map.mode.${key}`)}
            </button>
          ))}
        </div>
        <p className="mt-2 text-xs text-slate-500">{t(`map.mode.${mode}.caption`)}</p>
      </div>

      {!active ? (
        <p className="text-sm text-slate-500">{t("map.loading")}</p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200">
          <MapContainer
            center={FL_CENTER}
            zoom={6}
            style={{ height: "600px", width: "100%" }}
            scrollWheelZoom={false}
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            {mode === "impact" ? (
              <GeoJSON
                key="impact"
                data={counties as unknown as GeoJSON.GeoJsonObject}
                style={(feature) => {
                  const props = feature?.properties as CountyFeatureProperties;
                  const isStatewide = props?.scope_type === "statewide";
                  return {
                    fillColor: colorForImpact(props?.bill_count ?? 0),
                    fillOpacity: isStatewide ? 0.05 : 0.65,
                    color: isStatewide ? "#94a3b8" : "#334155",
                    weight: isStatewide ? 1 : 1.5,
                  } as PathOptions;
                }}
                onEachFeature={(feature, layer: Layer) => {
                  const props = feature.properties as CountyFeatureProperties;
                  if (props.scope_type === "statewide") return;
                  layer.bindTooltip(
                    t("map.tooltip.county", { name: props.scope_name, count: props.bill_count }),
                  );
                  layer.on("click", () => {
                    router.push(`/?geo=${encodeURIComponent(props.scope_name)}`);
                  });
                }}
              />
            ) : (
              <GeoJSON
                key="sponsorship"
                data={districts as unknown as GeoJSON.GeoJsonObject}
                style={(feature) => {
                  const props = feature?.properties as DistrictFeatureProperties;
                  return {
                    fillColor: colorForSponsorship(props?.bill_count ?? 0),
                    fillOpacity: 0.65,
                    color: "#334155",
                    weight: 1,
                  } as PathOptions;
                }}
                onEachFeature={(feature, layer: Layer) => {
                  const props = feature.properties as DistrictFeatureProperties;
                  const names = props.legislators.map((l) => l.name);
                  const who = names.length ? names.join(", ") : t("map.tooltip.noSponsor");
                  layer.bindTooltip(
                    t("map.tooltip.district", {
                      chamber: props.chamber,
                      name: props.scope_name,
                      who,
                      count: props.bill_count,
                    }) + (props.legislators.length ? t("map.tooltip.clickHint") : ""),
                  );
                  // A district can list more than one tracked legislator (a
                  // mid-session replacement, or a data hiccup) -- click
                  // filters to the first, alphabetically, same as the
                  // tooltip's lead name. No legislator means no filter to
                  // link to, so the district stays tooltip-only.
                  const primary = props.legislators[0];
                  if (primary) {
                    layer.on("click", () => {
                      router.push(
                        `/?sponsor=${encodeURIComponent(primary.entity_id)}` +
                          `&sponsorName=${encodeURIComponent(primary.name)}`,
                      );
                    });
                  }
                }}
              />
            )}
          </MapContainer>
        </div>
      )}
    </div>
  );
}
