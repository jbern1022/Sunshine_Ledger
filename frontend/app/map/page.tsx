"use client";

import dynamic from "next/dynamic";

import { t } from "@/lib/i18n";

// Leaflet touches `window` at import time, so the map must be client-only
// and skip server rendering entirely.
const MapView = dynamic(() => import("@/components/MapView"), { ssr: false });

export default function MapPage() {
  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-ledger-900">{t("map.page.title")}</h1>
        <p className="mt-1 text-sm text-slate-500">
          {t("map.page.intro")}
        </p>
      </div>
      <MapView />
    </div>
  );
}
