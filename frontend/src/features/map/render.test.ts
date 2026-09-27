import { describe, expect, it } from "vitest";
import type { FeatureLayer, RasterMapLayer } from "./layers/types";
import {
  ARROW_ICON,
  arrowImage,
  colorExpression,
  colorPaintProperty,
  radiusExpression,
  rasterLayerSpec,
  rasterSource,
  sourceId,
  styleLayerId,
  styleLayerIds,
  toMapLibreLayers,
} from "./render";

const base: FeatureLayer = {
  id: "quakes",
  label: "Earthquakes",
  group: "events",
  refreshMs: 60_000,
  defaultEnabled: false,
  style: { color: "#f97316", radius: 5 },
  load: async () => ({ type: "FeatureCollection", features: [] }),
};

describe("toMapLibreLayers", () => {
  it("renders plain layers as circles bound to their source", () => {
    expect(toMapLibreLayers(base, true)).toMatchObject([
      {
        id: styleLayerId("quakes"),
        source: sourceId("quakes"),
        type: "circle",
        layout: { visibility: "visible" },
        paint: { "circle-color": "#f97316", "circle-radius": 5 },
      },
    ]);
  });

  it("renders rotating layers as tinted arrows", () => {
    const layer = {
      ...base,
      style: { color: "#38bdf8", radius: 3, rotationProperty: "heading_deg" },
    };
    expect(toMapLibreLayers(layer, false)).toMatchObject([
      {
        type: "symbol",
        layout: {
          visibility: "none",
          "icon-image": ARROW_ICON,
          "icon-rotate": ["get", "heading_deg"],
        },
        paint: { "icon-color": "#38bdf8" },
      },
    ]);
    expect(colorPaintProperty(layer)).toBe("icon-color");
    expect(colorPaintProperty(base)).toBe("circle-color");
  });

  it("renders mixed layers as a line layer plus a point layer, filtered by geometry", () => {
    const cables = {
      ...base,
      id: "cables",
      style: { color: "#0ff", radius: 2, geometry: "mixed" as const },
    };
    const [line, points] = toMapLibreLayers(cables, true);
    expect(line).toMatchObject({ id: "argus-lyr-cables", type: "line" });
    expect(points).toMatchObject({
      id: "argus-lyr-cables-points",
      type: "circle",
      filter: ["==", ["geometry-type"], "Point"],
    });
    expect(styleLayerIds(cables)).toEqual(["argus-lyr-cables", "argus-lyr-cables-points"]);
    expect(styleLayerIds(base)).toEqual(["argus-lyr-quakes"]);
    const lineOnly = { ...cables, style: { ...cables.style, geometry: "line" as const } };
    expect(toMapLibreLayers(lineOnly, true)).toHaveLength(1);
  });
});

describe("expressions", () => {
  it("colours by category with a fallback", () => {
    const style = {
      color: "#999",
      radius: 3,
      colorBy: { property: "category", values: { flood: "#00f" } },
    };
    expect(colorExpression(style)).toEqual([
      "match",
      ["to-string", ["get", "category"]],
      "flood",
      "#00f",
      "#999",
    ]);
  });

  it("prefers a feature's own colour when it has one", () => {
    expect(colorExpression({ color: "#999", radius: 1, colorProperty: "color" })).toEqual([
      "coalesce",
      ["get", "color"],
      "#999",
    ]);
  });

  it("highlights watched keys over everything else", () => {
    const style = { color: "#999", radius: 3, highlight: { property: "watch_key", color: "#f00" } };
    expect(colorExpression(style, ["aircraft:abc123"])).toEqual([
      "case",
      ["in", ["to-string", ["get", "watch_key"]], ["literal", ["aircraft:abc123"]]],
      "#f00",
      "#999",
    ]);
    expect(colorExpression(style, [])).toBe("#999");
  });

  it("scales radius by a 0..1 property", () => {
    expect(
      radiusExpression({
        color: "#999",
        radius: 2,
        radiusBy: { property: "severity", min: 2, max: 10 },
      }),
    ).toEqual([
      "interpolate",
      ["linear"],
      ["coalesce", ["to-number", ["get", "severity"], 0], 0],
      0,
      2,
      1,
      10,
    ]);
    expect(radiusExpression({ color: "#999", radius: 4 })).toBe(4);
  });
});

describe("rasters", () => {
  const data = {
    tiles: ["https://t/{z}/{x}/{y}.png"],
    tileSize: 256,
    minZoom: 0,
    maxZoom: 7,
    attribution: "a",
    validAt: null,
    opacity: 0.7,
  };
  const layer: RasterMapLayer = {
    kind: "raster",
    id: "radar",
    label: "Radar",
    group: "imagery",
    refreshMs: 300_000,
    defaultEnabled: false,
    load: async () => data,
  };

  it("builds the source and the style layer", () => {
    expect(rasterSource(data)).toEqual({
      type: "raster",
      tiles: data.tiles,
      tileSize: 256,
      minzoom: 0,
      maxzoom: 7,
      attribution: "a",
    });
    expect(rasterLayerSpec(layer, false, 0.7)).toMatchObject({
      id: "argus-lyr-radar",
      type: "raster",
      layout: { visibility: "none" },
      paint: { "raster-opacity": 0.7 },
    });
    expect(styleLayerIds(layer)).toEqual(["argus-lyr-radar"]);
  });
});

describe("arrowImage", () => {
  it("produces an RGBA bitmap with an opaque body and transparent corners", () => {
    const { width, height, data } = arrowImage(24);
    expect(data).toHaveLength(width * height * 4);
    const alphaAt = (x: number, y: number) => data[(y * width + x) * 4 + 3];
    expect(alphaAt(0, 0)).toBe(0);
    expect(alphaAt(12, 18)).toBe(255);
  });
});
