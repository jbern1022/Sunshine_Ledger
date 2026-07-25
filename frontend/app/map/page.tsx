import dynamic from "next/dynamic";

// Leaflet touches `window` at import time, so the map must be client-only
// and skip server rendering entirely.
const MapView = dynamic(() => import("@/components/MapView"), { ssr: false });

export default function MapPage() {
  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-ledger-900">Impact map</h1>
        <p className="mt-1 text-sm text-slate-500">
          Counties shaded by number of tracked bills affecting them. Click a county to see its bills.
          County/district boundaries only — no per-address mapping at MVP.
        </p>
      </div>
      <MapView />
    </div>
  );
}
