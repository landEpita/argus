"use client";

import { useEffect, useRef, useState } from "react";
import type { ApiClient } from "@/lib/api/client";
import { clampBBox, roundPosition } from "@/lib/geo";
import type { LayerRegistry } from "../layers/registry";
import type { MapController, Selection } from "../MapCanvas";
import { LayerScheduler, type LayerUpdate } from "../scheduler";
import { loadCesium } from "./load";
import type { CesiumRenderer, CockpitState } from "./renderer";
import { heightForZoom, rectangleToBBox, zoomForHeight } from "./style";

/** Keyless satellite imagery (Esri World Imagery). */
const IMAGERY_URL =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
const IMAGERY_CREDIT = "Imagery © Esri, Maxar, Earthstar Geographics, and the GIS User Community";

interface Props {
  api: ApiClient;
  registry: LayerRegistry;
  initialEnabled: ReadonlySet<string>;
  initialPosition: { center: { lat: number; lon: number }; zoom: number };
  initialWatched: readonly string[];
  onReady(controller: MapController): void;
  onUpdate(update: LayerUpdate): void;
  onSelect(selection: Selection | null): void;
  onMove(position: { center: { lat: number; lon: number }; zoom: number }): void;
  onCockpit(state: CockpitState | null): void;
}

/**
 * The Cesium globe. Loaded only when chosen (Cesium is several megabytes),
 * with its workers and assets served from /cesium (see scripts/copy-cesium.mjs).
 */
export function CesiumCanvas(props: Props) {
  const container = useRef<HTMLDivElement>(null);
  const latest = useRef(props);
  const [status, setStatus] = useState<"loading" | "ready" | "failed">("loading");
  const [reason, setReason] = useState<string | null>(null);

  useEffect(() => {
    latest.current = { ...latest.current, ...props };
  });

  useEffect(() => {
    const p = latest.current;
    let disposed = false;
    let cleanup = () => {};

    (async () => {
      const [C, { CesiumRenderer: Renderer }, config] = await Promise.all([
        loadCesium(),
        import("./renderer"),
        p.api.mapConfig().catch(() => ({ cesium_ion_token: null })),
      ]);
      if (disposed || !container.current) return;
      const token = config.cesium_ion_token ?? null;
      if (token) C.Ion.defaultAccessToken = token;

      const viewer = new C.Viewer(container.current, {
        baseLayer: new C.ImageryLayer(
          new C.UrlTemplateImageryProvider({
            url: IMAGERY_URL,
            maximumLevel: 19,
            credit: new C.Credit(IMAGERY_CREDIT),
          }),
        ),
        terrain: token ? C.Terrain.fromWorldTerrain() : undefined,
        baseLayerPicker: false,
        geocoder: false,
        homeButton: false,
        sceneModePicker: false,
        navigationHelpButton: false,
        animation: false,
        timeline: false,
        fullscreenButton: false,
        infoBox: false,
        selectionIndicator: false,
        requestRenderMode: false,
      });
      viewer.scene.globe.enableLighting = false;
      if (viewer.scene.skyAtmosphere) viewer.scene.skyAtmosphere.show = true;
      if (token) {
        // Photorealistic 3D cities where Google has them; the imagery globe elsewhere.
        C.createGooglePhotorealistic3DTileset()
          .then((tiles) => {
            if (!disposed) viewer.scene.primitives.add(tiles);
          })
          .catch(() => {});
      }

      const renderer: CesiumRenderer = new Renderer(C, viewer, p.registry, (s) =>
        latest.current.onCockpit(s),
      );
      const scheduler = new LayerScheduler(p.registry, p.api, (update) => {
        renderer.apply(update);
        latest.current.onUpdate(update);
      });
      renderer.install(p.initialEnabled, p.initialWatched);

      viewer.camera.setView({
        destination: C.Cartesian3.fromDegrees(
          p.initialPosition.center.lon,
          p.initialPosition.center.lat,
          heightForZoom(p.initialPosition.zoom),
        ),
      });
      const viewport = () => {
        const rect = viewer.camera.computeViewRectangle(viewer.scene.globe.ellipsoid);
        return clampBBox(rectangleToBBox(rect));
      };
      const zoom = () => zoomForHeight(viewer.camera.positionCartographic.height);
      for (const id of p.initialEnabled) scheduler.enable(id);
      scheduler.setViewport(viewport(), zoom());

      const onMoveEnd = () => {
        if (renderer.inCockpit) return;
        scheduler.setViewport(viewport(), zoom());
        const c = viewer.camera.positionCartographic;
        latest.current.onMove(
          roundPosition(C.Math.toDegrees(c.latitude), C.Math.toDegrees(c.longitude), zoom()),
        );
      };
      viewer.camera.moveEnd.addEventListener(onMoveEnd);
      // While riding, the feeds follow the aircraft rather than the last map view.
      const follow = window.setInterval(() => {
        const box = renderer.cockpitViewport();
        if (box) scheduler.setViewport(clampBBox(box), 8);
      }, 10_000);

      const handler = new C.ScreenSpaceEventHandler(viewer.scene.canvas);
      handler.setInputAction((click: { position: { x: number; y: number } }) => {
        const picked = renderer.pick(click.position);
        latest.current.onSelect(
          picked
            ? {
                layer: picked.layer,
                properties: picked.properties,
                lat: picked.lat,
                lon: picked.lon,
              }
            : null,
        );
      }, C.ScreenSpaceEventType.LEFT_CLICK);

      latest.current.onReady({
        enable(id) {
          scheduler.enable(id);
          renderer.setVisible(id, true);
        },
        disable(id) {
          scheduler.disable(id);
          renderer.setVisible(id, false);
        },
        setProjection: () => {},
        flyTo: (lat, lon, z) => renderer.flyTo(lat, lon, z),
        fitBounds: (bounds) => renderer.fitBounds(bounds),
        showTrack: (features) => renderer.showTrack(features),
        setWatched: (keys) => renderer.setWatched(keys),
        enterCockpit: (layerId, id) => {
          const entered = renderer.enterCockpit(layerId, id);
          const box = renderer.cockpitViewport();
          if (box) scheduler.setViewport(clampBBox(box), 8);
          return entered;
        },
        exitCockpit: () => {
          renderer.exitCockpit();
          scheduler.setViewport(viewport(), zoom());
        },
      });
      setStatus("ready");

      cleanup = () => {
        window.clearInterval(follow);
        handler.destroy();
        viewer.camera.moveEnd.removeEventListener(onMoveEnd);
        scheduler.dispose();
        renderer.dispose();
        viewer.destroy();
      };
    })().catch((error: unknown) => {
      if (disposed) return;
      setReason(error instanceof Error ? error.message : String(error));
      setStatus("failed");
    });

    return () => {
      disposed = true;
      cleanup();
    };
  }, []);

  return (
    <div className="map cesium-map" data-testid="cesium-map">
      <link rel="stylesheet" href="/cesium/Widgets/widgets.css" precedence="default" />
      <div ref={container} className="cesium-container" />
      {status === "loading" && <p className="map-status">Loading the 3D globe…</p>}
      {status === "failed" && (
        <p className="map-status notice-warn">
          The 3D globe could not start here{reason ? ` (${reason})` : ""}. Switch back to 2D or 3D.
        </p>
      )}
    </div>
  );
}
