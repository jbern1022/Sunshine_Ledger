"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { MapContainer, TileLayer, GeoJSON } from "react-leaflet";
import type { Layer, PathOptions } from "leaflet";
import "leaflet/dist/leaflet.css";
import { fetchCountyGeoJSON } from "@/lib/api";
import type { CountyFeatureCollection, CountyFeatureProperties } from "@/lib/types";

const FL_CENTER: [number, number] = [27.8, -81.7];

function colorForCount(count: number): string {
  if (count === 0) return "#e2e8f0"; // slate-200
  if (count === 1) return "#fde68a"; // amber-200
  if (count <= 3) return "#f5c518"; // sunshine-400
  return "#b58200"; // sunshine-600
}

export default function MapView() {
  const router = useRouter();
  const [data, setData] = useState<CountyFeatureCollection | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchCountyGeoJSON()
      .then(setData)
      .catch((err) => setError(err.message ?? "Failed to load map data"));
  }, []);

  if (error) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        {error} — make sure the backend is running and boundaries are loaded (
        <code>python -m app.pipeline.load_boundaries</code> or via <code>seed.py</code>).
      </div>
    );
  }

  if (!data) return <p className="text-sm text-slate-400">Loading map…</p>;

  // react-leaflet types its GeoJSON `data` prop loosely; cast is safe since our
  // FeatureCollection shape matches the GeoJSON spec.
  const geoData = data as unknown as GeoJSON.GeoJsonObject;

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200">
      <MapContainer center={FL_CENTER} zoom={6} style={{ height: "600px", width: "100%" }} scrollWheelZoom={false}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <GeoJSON
          data={geoData}
          style={(feature) => {
            const props = feature?.properties as CountyFeatureProperties;
            const isStatewide = props?.scope_type === "statewide";
            return {
              fillColor: colorForCount(props?.bill_count ?? 0),
              fillOpacity: isStatewide ? 0.05 : 0.65,
              color: isStatewide ? "#94a3b8" : "#334155",
              weight: isStatewide ? 1 : 1.5,
            } as PathOptions;
          }}
          onEachFeature={(feature, layer: Layer) => {
            const props = feature.properties as CountyFeatureProperties;
            if (props.scope_type === "statewide") return;
            layer.bindTooltip(`${props.scope_name}: ${props.bill_count} bill${props.bill_count === 1 ? "" : "s"}`);
            layer.on("click", () => {
              router.push(`/?geo=${encodeURIComponent(props.scope_name)}`);
            });
          }}
        />
      </MapContainer>
    </div>
  );
}
