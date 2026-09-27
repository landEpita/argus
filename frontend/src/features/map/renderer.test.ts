import type { Map as MapLibreMap } from "maplibre-gl";
import { describe, expect, it, vi } from "vitest";
import { createLayerRegistry } from "./layers/registry";
import type { FeatureLayer, LayerFeatures, RasterData, RasterMapLayer } from "./layers/types";
import { MapLibreRenderer, TRACK_SOURCE } from "./renderer";

/** Just enough of MapLibre's Map to observe what the renderer does. */
class FakeMap {
  readonly sources = new Map<string, { spec: unknown; data?: unknown; tiles?: string[] }>();
  readonly layers: { id: string; before?: string; spec: Record<string, unknown> }[] = [];
  readonly layout: Record<string, unknown> = {};
  readonly paint: Record<string, unknown> = {};
  readonly handlers: Record<string, ((e: unknown) => void)[]> = {};
  projection: unknown = null;
  images = new Set<string>();
  canvas = { style: { cursor: "" } };

  hasImage = (id: string) => this.images.has(id);
  addImage = (id: string) => void this.images.add(id);
  addSource = (id: string, spec: unknown) => void this.sources.set(id, { spec });
  getSource = (id: string) => {
    const source = this.sources.get(id);
    if (!source) return undefined;
    return {
      setData: (data: unknown) => {
        source.data = data;
      },
      setTiles: (tiles: string[]) => {
        source.tiles = tiles;
      },
    };
  };
  addLayer = (spec: Record<string, unknown>, before?: string) => {
    this.layers.push({ id: String(spec.id), before, spec });
  };
  getLayer = (id: string) => this.layers.find((l) => l.id === id);
  setLayoutProperty = (id: string, prop: string, value: unknown) => {
    this.layout[`${id}.${prop}`] = value;
  };
  setPaintProperty = (id: string, prop: string, value: unknown) => {
    this.paint[`${id}.${prop}`] = value;
  };
  on = (event: string, id: string, handler: (e: unknown) => void) => {
    const key = `${event}:${id}`;
    this.handlers[key] = [...(this.handlers[key] ?? []), handler];
  };
  getCanvas = () => this.canvas;
  flights: unknown[] = [];
  flyTo = (options: unknown) => {
    this.flights.push(options);
  };
  setProjection = (p: unknown) => {
    this.projection = p;
  };
}

const EMPTY: LayerFeatures = { type: "FeatureCollection", features: [] };
const feature = (id: string, extra: Partial<FeatureLayer> = {}): FeatureLayer => ({
  id,
  label: id,
  group: "movement",
  refreshMs: 5_000,
  defaultEnabled: false,
  style: { color: "#fff", radius: 3, highlight: { property: "watch_key", color: "#f00" } },
  load: async () => EMPTY,
  ...extra,
});
const RADAR: RasterData = {
  tiles: ["https://r/1/{z}/{x}/{y}.png"],
  tileSize: 256,
  minZoom: 0,
  maxZoom: 7,
  attribution: "r",
  validAt: "2026-09-27T16:00:00Z",
  opacity: 0.7,
};
const radar: RasterMapLayer = {
  kind: "raster",
  id: "radar",
  label: "Radar",
  group: "imagery",
  refreshMs: 300_000,
  defaultEnabled: false,
  load: async () => RADAR,
};

function setup() {
  const map = new FakeMap();
  const registry = createLayerRegistry([feature("aircraft"), feature("quakes"), radar]);
  const renderer = new MapLibreRenderer(map as unknown as MapLibreMap, registry);
  renderer.install(new Set(["aircraft", "radar"]), ["aircraft:abc123"]);
  return { map, renderer };
}

describe("MapLibreRenderer", () => {
  it("installs a source and style layer per feature layer, plus the track overlay", () => {
    const { map } = setup();
    expect([...map.sources.keys()]).toEqual([
      "argus-src-aircraft",
      "argus-src-quakes",
      TRACK_SOURCE,
    ]);
    expect(map.layers.map((l) => l.id)).toEqual([
      "argus-lyr-aircraft",
      "argus-lyr-quakes",
      `${TRACK_SOURCE}-line`,
      `${TRACK_SOURCE}-start`,
    ]);
    expect(map.getLayer("argus-lyr-aircraft")?.spec.layout).toMatchObject({
      visibility: "visible",
    });
    expect(map.getLayer("argus-lyr-quakes")?.spec.layout).toMatchObject({ visibility: "none" });
    expect(map.images.has("argus-arrow")).toBe(true);
  });

  it("pushes feature data into the layer's source", () => {
    const { map, renderer } = setup();
    const data = { ...EMPTY, features: [] };
    renderer.apply({ layerId: "aircraft", status: "ready", data, loadedAt: 1 });
    expect(map.sources.get("argus-src-aircraft")?.data).toBe(data);
  });

  it("clears features when the map is zoomed out past the layer", () => {
    const { map, renderer } = setup();
    map.getSource("argus-src-quakes")?.setData("stale");
    renderer.apply({ layerId: "quakes", status: "zoom" });
    expect(map.sources.get("argus-src-quakes")?.data).toEqual(EMPTY);
  });

  it("adds a raster below the data layers on first data, then only swaps its tiles", () => {
    const { map, renderer } = setup();
    renderer.apply({ layerId: "radar", status: "ready", data: RADAR, loadedAt: 1 });
    const added = map.getLayer("argus-lyr-radar");
    expect(added?.before).toBe("argus-lyr-aircraft");
    expect(added?.spec.layout).toMatchObject({ visibility: "visible" });

    renderer.apply({ layerId: "radar", status: "ready", data: RADAR, loadedAt: 2 });
    expect(map.sources.get("argus-src-radar")?.tiles).toBeUndefined(); // unchanged frame
    const next = { ...RADAR, tiles: ["https://r/2/{z}/{x}/{y}.png"] };
    renderer.apply({ layerId: "radar", status: "ready", data: next, loadedAt: 3 });
    expect(map.sources.get("argus-src-radar")?.tiles).toEqual(next.tiles);
    expect(map.layers.filter((l) => l.id === "argus-lyr-radar")).toHaveLength(1);
  });

  it("remembers visibility for rasters that are not on the map yet", () => {
    const { map, renderer } = setup();
    renderer.setVisible("radar", false);
    renderer.apply({ layerId: "radar", status: "ready", data: RADAR, loadedAt: 1 });
    expect(map.getLayer("argus-lyr-radar")?.spec.layout).toMatchObject({ visibility: "none" });
    renderer.setVisible("quakes", true);
    expect(map.layout["argus-lyr-quakes.visibility"]).toBe("visible");
  });

  it("recolours highlightable layers when the watchlist changes", () => {
    const { map, renderer } = setup();
    renderer.setWatched(["vessel:227006760"]);
    expect(JSON.stringify(map.paint["argus-lyr-aircraft.circle-color"])).toContain(
      "vessel:227006760",
    );
  });

  it("shows and hides the selected track", () => {
    const { map, renderer } = setup();
    const track = { ...EMPTY, features: [] };
    renderer.showTrack(track);
    expect(map.sources.get(TRACK_SOURCE)?.data).toBe(track);
    renderer.showTrack(null);
    expect(map.sources.get(TRACK_SOURCE)?.data).toEqual(EMPTY);
  });

  it("switches projection", () => {
    const { map, renderer } = setup();
    renderer.setProjection("globe");
    expect(map.projection).toEqual({ type: "globe" });
  });

  it("defers a projection chosen before the style loaded", () => {
    const map = new FakeMap();
    const renderer = new MapLibreRenderer(map as unknown as MapLibreMap, createLayerRegistry([]));
    renderer.setProjection("globe");
    expect(map.projection).toBeNull();
    renderer.install(new Set(), []);
    expect(map.projection).toEqual({ type: "globe" });
  });

  it("routes clicks on feature layers to the handler, with the layer", () => {
    const { map, renderer } = setup();
    const handler = vi.fn();
    renderer.onFeatureClick(handler);
    const lngLat = { lng: 1, lat: 2 };
    map.handlers["click:argus-lyr-quakes"]?.[0]?.({
      features: [{ properties: { title: "M5" } }],
      lngLat,
    });
    expect(handler).toHaveBeenCalledWith(
      expect.objectContaining({ id: "quakes" }),
      { title: "M5" },
      lngLat,
    );
    map.handlers["mouseenter:argus-lyr-quakes"]?.[0]?.({});
    expect(map.canvas.style.cursor).toBe("pointer");
    expect(map.handlers["click:argus-lyr-radar"]).toBeUndefined();
  });

  it("flies to a point", () => {
    const { map, renderer } = setup();
    renderer.flyTo(46, 2, 4);
    expect(map.flights).toEqual([{ center: [2, 46], zoom: 4, essential: true }]);
  });

  it("draws area layers beneath everything else", () => {
    const map = new FakeMap();
    const area = feature("areas", { style: { color: "#f00", radius: 0, geometry: "polygon" } });
    const registry = createLayerRegistry([feature("aircraft"), area, radar]);
    new MapLibreRenderer(map as unknown as MapLibreMap, registry).install(new Set(), []);
    expect(map.layers.map((l) => l.id).slice(0, 3)).toEqual([
      "argus-lyr-areas",
      "argus-lyr-areas-outline",
      "argus-lyr-aircraft",
    ]);
  });

  it("ignores updates for unknown layers", () => {
    const { renderer } = setup();
    expect(() =>
      renderer.apply({ layerId: "ghost", status: "ready", data: EMPTY, loadedAt: 1 }),
    ).not.toThrow();
  });
});
