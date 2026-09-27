"use client";

import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";
import type { ApiClient } from "@/lib/api/client";
import { clampBBox, roundPosition } from "@/lib/geo";
import type { LayerRegistry } from "./layers/registry";
import type { FeatureLayer, LayerFeatures } from "./layers/types";
import { MapLibreRenderer, type Projection } from "./renderer";
import { LayerScheduler, type LayerUpdate } from "./scheduler";

export const BASEMAP_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

/** A clicked feature, for the inspector. */
export interface Selection {
  layer: FeatureLayer;
  properties: Record<string, unknown>;
  lat: number;
  lon: number;
}

/** What the cockpit can ask of the map, once it is ready. */
export interface MapController {
  enable(id: string): void;
  disable(id: string): void;
  setProjection(projection: Projection): void;
  flyTo(lat: number, lon: number, zoom: number): void;
  fitBounds(bounds: readonly [number, number, number, number]): void;
  showTrack(features: LayerFeatures | null): void;
  setWatched(keys: readonly string[]): void;
}

declare global {
  interface Window {
    /** Set only in end-to-end builds, so tests can click on map features. */
    __argusMap?: maplibregl.Map;
  }
}

interface Props {
  api: ApiClient;
  registry: LayerRegistry;
  initialEnabled: ReadonlySet<string>;
  initialProjection: Projection;
  initialPosition: { center: { lat: number; lon: number }; zoom: number };
  initialWatched: readonly string[];
  onReady(controller: MapController): void;
  onUpdate(update: LayerUpdate): void;
  onSelect(selection: Selection | null): void;
  onMove(position: { center: { lat: number; lon: number }; zoom: number }): void;
}

/**
 * The map and nothing else: MapLibre, the renderer and the layer scheduler.
 * Everything around it (panels, inspector) talks to it through a controller,
 * so the React tree above never re-creates the map.
 */
export function MapCanvas(props: Props) {
  const container = useRef<HTMLDivElement>(null);
  const initial = useRef(props);

  useEffect(() => {
    const p = initial.current;
    if (!container.current) return;
    const map = new maplibregl.Map({
      container: container.current,
      style: BASEMAP_STYLE,
      center: [p.initialPosition.center.lon, p.initialPosition.center.lat],
      zoom: p.initialPosition.zoom,
      attributionControl: { compact: true },
    });
    if (process.env.NEXT_PUBLIC_E2E === "1") window.__argusMap = map;

    const renderer = new MapLibreRenderer(map, p.registry);
    renderer.setProjection(p.initialProjection);
    const scheduler = new LayerScheduler(p.registry, p.api, (update) => {
      renderer.apply(update);
      initial.current.onUpdate(update);
    });
    const viewport = () => {
      const b = map.getBounds();
      return clampBBox({
        west: b.getWest(),
        south: b.getSouth(),
        east: b.getEast(),
        north: b.getNorth(),
      });
    };

    let clickedFeature = false;
    map.on("load", () => {
      renderer.install(p.initialEnabled, p.initialWatched);
      renderer.onFeatureClick((layer, properties, at) => {
        clickedFeature = true;
        initial.current.onSelect({ layer, properties, lat: at.lat, lon: at.lng });
      });
      for (const id of p.initialEnabled) scheduler.enable(id);
      scheduler.setViewport(viewport(), map.getZoom());
      initial.current.onReady({
        enable(id) {
          scheduler.enable(id);
          renderer.setVisible(id, true);
        },
        disable(id) {
          scheduler.disable(id);
          renderer.setVisible(id, false);
        },
        setProjection: (projection) => renderer.setProjection(projection),
        flyTo: (lat, lon, zoom) => renderer.flyTo(lat, lon, zoom),
        fitBounds: ([w, s, e, n]) =>
          map.fitBounds(
            [
              [w, s],
              [e, n],
            ],
            { padding: 40, duration: 1200 },
          ),
        showTrack: (features) => renderer.showTrack(features),
        setWatched: (keys) => {
          if (map.isStyleLoaded()) renderer.setWatched(keys);
        },
      });
    });
    // A click on empty map clears the selection; feature clicks fire first.
    map.on("click", () => {
      if (!clickedFeature) initial.current.onSelect(null);
      clickedFeature = false;
    });
    map.on("moveend", () => {
      scheduler.setViewport(viewport(), map.getZoom());
      const c = map.getCenter();
      initial.current.onMove(roundPosition(c.lat, c.lng, map.getZoom()));
    });

    return () => {
      scheduler.dispose();
      map.remove();
      if (window.__argusMap === map) window.__argusMap = undefined;
    };
  }, []);

  // Keep the latest callbacks without re-creating the map.
  useEffect(() => {
    initial.current = { ...initial.current, ...props };
  });

  return <div ref={container} className="map" data-testid="map" />;
}
