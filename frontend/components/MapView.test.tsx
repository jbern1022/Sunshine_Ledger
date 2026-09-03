import type { ReactNode } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MapView from "./MapView";
import * as api from "@/lib/api";
import type { CountyFeatureCollection, DistrictFeatureCollection } from "@/lib/types";

const { pushMock } = vi.hoisted(() => ({ pushMock: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

vi.mock("@/lib/api", () => ({
  fetchCountyGeoJSON: vi.fn(),
  fetchDistrictGeoJSON: vi.fn(),
}));

// Leaflet doesn't run under jsdom, and the logic actually worth regression
// coverage (color-bucket thresholds, skipping statewide tooltips, the lazy
// district fetch, tooltip text, click wiring) lives in the style()/
// onEachFeature() callbacks MapView hands to react-leaflet's <GeoJSON>, not
// in Leaflet's own canvas rendering. This mock invokes those callbacks once
// per feature the same way Leaflet would, and surfaces the result as plain
// buttons so tests can assert on real behavior without a real map. See the
// "MapView test strategy" note in Notion for why this shape was chosen over
// either skipping map tests entirely or fighting jsdom+Leaflet directly.
type MockFeature = { properties: Record<string, unknown> };
type MockGeoJSONData = { features: MockFeature[] };
type MockLayer = {
  tooltip?: string;
  onClick?: () => void;
  bindTooltip: (text: string) => void;
  on: (event: string, handler: () => void) => void;
};

vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  TileLayer: () => null,
  GeoJSON: ({
    data,
    style,
    onEachFeature,
  }: {
    data: MockGeoJSONData;
    style?: (feature: MockFeature) => { fillColor?: string };
    onEachFeature?: (feature: MockFeature, layer: MockLayer) => void;
  }) => (
    <div data-testid="geojson">
      {data.features.map((feature, i) => {
        const computedStyle = style?.(feature) ?? {};
        const layer: MockLayer = {
          bindTooltip(text) {
            layer.tooltip = text;
          },
          on(event, handler) {
            if (event === "click") layer.onClick = handler;
          },
        };
        onEachFeature?.(feature, layer);
        return (
          <button
            key={i}
            data-testid={`feature-${i}`}
            data-fill-color={computedStyle.fillColor}
            onClick={() => layer.onClick?.()}
          >
            {layer.tooltip ?? "(no tooltip)"}
          </button>
        );
      })}
    </div>
  ),
}));

const countiesFixture: CountyFeatureCollection = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: {},
      properties: { scope_type: "statewide", scope_name: "FL", bill_count: 0, source: null },
    },
    {
      type: "Feature",
      geometry: {},
      properties: { scope_type: "county", scope_name: "Miami-Dade County", bill_count: 1, source: "tiger" },
    },
    {
      type: "Feature",
      geometry: {},
      properties: { scope_type: "county", scope_name: "Duval County", bill_count: 5, source: "tiger" },
    },
  ],
};

const districtsFixture: DistrictFeatureCollection = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: {},
      properties: {
        scope_type: "state_house",
        scope_name: "District 10",
        chamber: "House",
        bill_count: 20,
        legislators: ["Jane Smith"],
        source: "tiger",
      },
    },
    {
      type: "Feature",
      geometry: {},
      properties: {
        scope_type: "state_house",
        scope_name: "District 99",
        chamber: "House",
        bill_count: 0,
        legislators: [],
        source: "tiger",
      },
    },
  ],
};

describe("MapView", () => {
  beforeEach(() => {
    vi.mocked(api.fetchCountyGeoJSON).mockReset();
    vi.mocked(api.fetchDistrictGeoJSON).mockReset();
    pushMock.mockReset();
  });

  it("shows a loading message before county data arrives", () => {
    vi.mocked(api.fetchCountyGeoJSON).mockReturnValueOnce(new Promise(() => {}));
    render(<MapView />);
    expect(screen.getByText(/loading map/i)).toBeInTheDocument();
  });

  it("shows an error message with a recovery hint when county data fails to load", async () => {
    vi.mocked(api.fetchCountyGeoJSON).mockRejectedValueOnce(new Error("Failed to fetch map data: 500"));
    render(<MapView />);

    expect(await screen.findByText(/failed to fetch map data: 500/i)).toBeInTheDocument();
    expect(screen.getByText(/make sure the backend is running/i)).toBeInTheDocument();
    expect(screen.getByText(/load_boundaries/i)).toBeInTheDocument();
  });

  it("colors counties by bill count and skips tooltips for statewide rows", async () => {
    vi.mocked(api.fetchCountyGeoJSON).mockResolvedValueOnce(countiesFixture);
    render(<MapView />);
    await screen.findByTestId("geojson");

    const statewide = screen.getByTestId("feature-0");
    expect(statewide).toHaveTextContent("(no tooltip)");

    const miamiDade = screen.getByTestId("feature-1");
    expect(miamiDade).toHaveTextContent("Miami-Dade County: 1 bill");
    expect(miamiDade).toHaveAttribute("data-fill-color", "#fde68a");

    const duval = screen.getByTestId("feature-2");
    expect(duval).toHaveTextContent("Duval County: 5 bills");
    expect(duval).toHaveAttribute("data-fill-color", "#b58200");
  });

  it("navigates to the filtered browse page when a non-statewide county is clicked", async () => {
    vi.mocked(api.fetchCountyGeoJSON).mockResolvedValueOnce(countiesFixture);
    const user = userEvent.setup();
    render(<MapView />);
    await screen.findByTestId("geojson");

    await user.click(screen.getByTestId("feature-2"));
    expect(pushMock).toHaveBeenCalledWith("/?geo=Duval%20County");
  });

  it("does not navigate when a statewide row is clicked, since it never registers a click handler", async () => {
    vi.mocked(api.fetchCountyGeoJSON).mockResolvedValueOnce(countiesFixture);
    const user = userEvent.setup();
    render(<MapView />);
    await screen.findByTestId("geojson");

    await user.click(screen.getByTestId("feature-0"));
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("reflects the active mode via aria-pressed and swaps the caption", async () => {
    vi.mocked(api.fetchCountyGeoJSON).mockResolvedValueOnce(countiesFixture);
    vi.mocked(api.fetchDistrictGeoJSON).mockResolvedValueOnce(districtsFixture);
    const user = userEvent.setup();
    render(<MapView />);
    await screen.findByTestId("geojson");

    const group = screen.getByRole("group", { name: /map view/i });
    expect(within(group).getByRole("button", { name: /impact by county/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByText(/click a county to see its bills/i)).toBeInTheDocument();

    await user.click(within(group).getByRole("button", { name: /sponsorship by district/i }));

    expect(within(group).getByRole("button", { name: /sponsorship by district/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(within(group).getByRole("button", { name: /impact by county/i })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(screen.getByText(/who introduces legislation, not who it affects/i)).toBeInTheDocument();
  });

  it("lazily fetches district data only on the first switch to sponsorship mode, then caches it", async () => {
    vi.mocked(api.fetchCountyGeoJSON).mockResolvedValueOnce(countiesFixture);
    vi.mocked(api.fetchDistrictGeoJSON).mockResolvedValueOnce(districtsFixture);
    const user = userEvent.setup();
    render(<MapView />);
    await screen.findByTestId("geojson");

    expect(api.fetchDistrictGeoJSON).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /sponsorship by district/i }));
    await waitFor(() => expect(api.fetchDistrictGeoJSON).toHaveBeenCalledTimes(1));
    await screen.findByText(/sponsored 20 tracked bills/i);

    await user.click(screen.getByRole("button", { name: /impact by county/i }));
    await user.click(screen.getByRole("button", { name: /sponsorship by district/i }));

    expect(api.fetchDistrictGeoJSON).toHaveBeenCalledTimes(1);
  });

  it("falls back to 'no tracked sponsor' for a district with no listed legislators, and it isn't clickable", async () => {
    vi.mocked(api.fetchCountyGeoJSON).mockResolvedValueOnce(countiesFixture);
    vi.mocked(api.fetchDistrictGeoJSON).mockResolvedValueOnce(districtsFixture);
    const user = userEvent.setup();
    render(<MapView />);
    await screen.findByTestId("geojson");

    await user.click(screen.getByRole("button", { name: /sponsorship by district/i }));
    const emptyDistrict = await screen.findByText(/no tracked sponsor/i);

    expect(emptyDistrict).toHaveTextContent("House District 99 — no tracked sponsor: sponsored 0 tracked bills");

    await user.click(emptyDistrict);
    expect(pushMock).not.toHaveBeenCalled();
  });
});
