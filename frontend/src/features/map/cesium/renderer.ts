/**
 * The second renderer: the same layers on a Cesium globe, with satellite
 * imagery, aircraft at their reported altitude and a cockpit view.
 *
 * It implements the surface the MapLibre renderer does (apply an update,
 * visibility, watched highlight, track, fly to) so the scheduler and the
 * cockpit shell do not know which one is drawing. Points and lines are drawn;
 * areas (choropleths, camera cones) and tile overlays stay on the 2D/3D map.
 */
import type * as CesiumNS from "cesium";
import {
  type Contact,
  contacts,
  extrapolate,
  eyeHeight,
  type Fix,
  fixFrom,
  MAX_EXTRAPOLATION_S,
} from "../cockpit";
import type { LayerRegistry } from "../layers/registry";
import {
  type FeatureLayer,
  isRasterData,
  isRasterLayer,
  type LayerFeatures,
} from "../layers/types";
import type { LayerUpdate } from "../scheduler";
import { featureColor, featureHeight, featureSize, heightForZoom } from "./style";

type Cesium = typeof CesiumNS;

/** What a picked primitive carries back to the inspector. */
export interface PickedFeature {
  layer: FeatureLayer;
  id: string;
  properties: Record<string, unknown>;
  lat: number;
  lon: number;
}

export interface CockpitState {
  fix: Fix;
  /** Seconds since the feed last reported this aircraft. */
  reportAgeS: number;
  extrapolated: boolean;
  contacts: Contact[];
  /** The aircraft has left the feed; the view holds its last position. */
  lost: boolean;
}

interface LayerPrimitives {
  points: CesiumNS.PointPrimitiveCollection;
  arrows: CesiumNS.BillboardCollection;
  lines: CesiumNS.PolylineCollection;
  data: LayerFeatures | null;
  loadedAt: number;
}

const COCKPIT_PITCH_DEG = -3;
const HUD_EVERY_MS = 500;

function arrowCanvas(): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 32;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    ctx.fillStyle = "#fff";
    ctx.beginPath();
    ctx.moveTo(16, 2);
    ctx.lineTo(27, 29);
    ctx.lineTo(16, 23);
    ctx.lineTo(5, 29);
    ctx.closePath();
    ctx.fill();
  }
  return canvas;
}

export class CesiumRenderer {
  private readonly layers = new Map<string, LayerPrimitives>();
  private readonly visible = new Set<string>();
  private watched: ReadonlySet<string> = new Set();
  private readonly track: CesiumNS.PolylineCollection;
  private readonly arrow = arrowCanvas();
  private cockpit: { layerId: string; id: string; fix: Fix; lostAt: number | null } | null = null;
  private lastHud = 0;
  private removePreRender: (() => void) | null = null;

  constructor(
    private readonly C: Cesium,
    private readonly viewer: CesiumNS.Viewer,
    private readonly registry: LayerRegistry,
    private readonly onCockpit: (state: CockpitState | null) => void,
  ) {
    this.track = viewer.scene.primitives.add(new C.PolylineCollection());
  }

  install(enabled: ReadonlySet<string>, watched: readonly string[]): void {
    this.watched = new Set(watched);
    for (const layer of this.registry.all()) {
      if (isRasterLayer(layer)) continue;
      if (enabled.has(layer.id)) this.visible.add(layer.id);
      const scene = this.viewer.scene;
      const primitives: LayerPrimitives = {
        points: scene.primitives.add(new this.C.PointPrimitiveCollection()),
        arrows: scene.primitives.add(new this.C.BillboardCollection({ scene })),
        lines: scene.primitives.add(new this.C.PolylineCollection()),
        data: null,
        loadedAt: 0,
      };
      this.layers.set(layer.id, primitives);
      this.showLayer(layer.id, this.visible.has(layer.id));
    }
    const listener = () => this.frame();
    this.viewer.scene.preRender.addEventListener(listener);
    this.removePreRender = () => this.viewer.scene.preRender.removeEventListener(listener);
  }

  dispose(): void {
    this.removePreRender?.();
  }

  apply(update: LayerUpdate): void {
    const layer = this.registry.get(update.layerId);
    const primitives = this.layers.get(update.layerId);
    if (!layer || isRasterLayer(layer) || !primitives) return;
    if (update.status === "zoom") this.draw(layer, primitives, null, 0);
    if (update.status !== "ready" || isRasterData(update.data)) return;
    this.draw(layer, primitives, update.data, update.loadedAt);
    if (this.cockpit?.layerId === layer.id) this.refreshCockpitFix(update.data, update.loadedAt);
  }

  setVisible(layerId: string, on: boolean): void {
    if (on) this.visible.add(layerId);
    else this.visible.delete(layerId);
    this.showLayer(layerId, on);
  }

  setWatched(keys: readonly string[]): void {
    this.watched = new Set(keys);
    for (const layer of this.registry.all()) {
      const primitives = this.layers.get(layer.id);
      if (!isRasterLayer(layer) && primitives?.data && layer.style.highlight) {
        this.draw(layer, primitives, primitives.data, primitives.loadedAt);
      }
    }
  }

  showTrack(features: LayerFeatures | null): void {
    const C = this.C;
    this.track.removeAll();
    for (const f of features?.features ?? []) {
      if (f.geometry.type !== "LineString") continue;
      const heights = f.geometry.coordinates.map(([lon = 0, lat = 0, alt]) =>
        C.Cartesian3.fromDegrees(lon, lat, typeof alt === "number" ? alt : 0),
      );
      this.track.add({ positions: heights, width: 2.5, material: this.material("#f472b6") });
    }
  }

  flyTo(lat: number, lon: number, zoom: number): void {
    this.viewer.camera.flyTo({
      destination: this.C.Cartesian3.fromDegrees(lon, lat, heightForZoom(zoom)),
      duration: 1.2,
    });
  }

  fitBounds([w, s, e, n]: readonly [number, number, number, number]): void {
    this.viewer.camera.flyTo({
      destination: this.C.Rectangle.fromDegrees(w, s, e, n),
      duration: 1.2,
    });
  }

  pick(position: { x: number; y: number }): PickedFeature | null {
    const picked = this.viewer.scene.pick(new this.C.Cartesian2(position.x, position.y));
    const id = picked?.id as PickedFeature | undefined;
    return id && typeof id === "object" && "layer" in id ? id : null;
  }

  // ── Cockpit ──

  enterCockpit(layerId: string, id: string): boolean {
    const data = this.layers.get(layerId)?.data;
    const feature = data?.features.find((f) => f.id === id);
    if (feature?.geometry.type !== "Point") return false;
    const [lon = 0, lat = 0] = feature.geometry.coordinates;
    const at = this.layers.get(layerId)?.loadedAt ?? Date.now();
    this.cockpit = {
      layerId,
      id,
      fix: fixFrom(id, feature.properties, lat, lon, at),
      lostAt: null,
    };
    const controller = this.viewer.scene.screenSpaceCameraController;
    controller.enableRotate = controller.enableTranslate = controller.enableZoom = false;
    controller.enableTilt = false;
    controller.enableLook = true; // the pilot may look around; the aircraft keeps flying
    this.redrawLayer(layerId);
    return true;
  }

  exitCockpit(): void {
    const state = this.cockpit;
    if (!state) return;
    this.cockpit = null;
    const controller = this.viewer.scene.screenSpaceCameraController;
    controller.enableRotate = controller.enableTranslate = controller.enableZoom = true;
    controller.enableTilt = true;
    this.redrawLayer(state.layerId);
    this.onCockpit(null);
    const { lat, lon } = state.fix;
    this.viewer.camera.flyTo({
      destination: this.C.Cartesian3.fromDegrees(lon, lat, 60_000),
      duration: 1,
    });
  }

  /** The box the feeds should cover while riding: 250 km around the aircraft. */
  cockpitViewport(): { west: number; south: number; east: number; north: number } | null {
    const fix = this.cockpit?.fix;
    if (!fix) return null;
    const dLat = 250 / 111.2;
    const dLon = dLat / Math.max(0.2, Math.cos((fix.lat * Math.PI) / 180));
    return {
      west: Math.max(-180, fix.lon - dLon),
      south: Math.max(-85, fix.lat - dLat),
      east: Math.min(180, fix.lon + dLon),
      north: Math.min(85, fix.lat + dLat),
    };
  }

  get inCockpit(): boolean {
    return this.cockpit !== null;
  }

  private refreshCockpitFix(data: LayerFeatures, loadedAt: number): void {
    const state = this.cockpit;
    if (!state) return;
    const feature = data.features.find((f) => f.id === state.id);
    if (feature?.geometry.type !== "Point") {
      state.lostAt ??= Date.now();
      return;
    }
    const [lon = 0, lat = 0] = feature.geometry.coordinates;
    state.fix = fixFrom(state.id, feature.properties, lat, lon, loadedAt);
    state.lostAt = null;
  }

  private frame(): void {
    const state = this.cockpit;
    if (!state) return;
    const now = Date.now();
    const at = state.lostAt === null ? extrapolate(state.fix, now) : state.fix;
    const heading = state.fix.headingDeg ?? this.C.Math.toDegrees(this.viewer.camera.heading);
    this.viewer.camera.setView({
      destination: this.C.Cartesian3.fromDegrees(at.lon, at.lat, eyeHeight(state.fix)),
      orientation: {
        heading: this.C.Math.toRadians(heading),
        pitch: this.C.Math.toRadians(COCKPIT_PITCH_DEG),
        roll: 0,
      },
    });
    if (now - this.lastHud < HUD_EVERY_MS) return;
    this.lastHud = now;
    const reportAgeS = Math.max(0, (now - state.fix.at) / 1000);
    this.onCockpit({
      fix: state.fix,
      reportAgeS,
      extrapolated:
        state.lostAt === null &&
        !!state.fix.speedMs &&
        reportAgeS > 1 &&
        reportAgeS <= MAX_EXTRAPOLATION_S,
      contacts: contacts(state.fix, this.fixes()),
      lost: state.lostAt !== null,
    });
  }

  /** Every aircraft currently drawn, as fixes, for the contact list. */
  private fixes(): Fix[] {
    const out: Fix[] = [];
    for (const layer of this.registry.all()) {
      if (isRasterLayer(layer) || layer.watchable !== "aircraft" || !this.visible.has(layer.id))
        continue;
      const primitives = this.layers.get(layer.id);
      for (const f of primitives?.data?.features ?? []) {
        if (f.geometry.type !== "Point") continue;
        const [lon = 0, lat = 0] = f.geometry.coordinates;
        out.push(fixFrom(String(f.id), f.properties, lat, lon, primitives?.loadedAt ?? 0));
      }
    }
    return out;
  }

  // ── Drawing ──

  private redrawLayer(layerId: string): void {
    const layer = this.registry.get(layerId);
    const primitives = this.layers.get(layerId);
    if (layer && !isRasterLayer(layer) && primitives?.data) {
      this.draw(layer, primitives, primitives.data, primitives.loadedAt);
    }
  }

  private showLayer(layerId: string, on: boolean): void {
    const p = this.layers.get(layerId);
    if (!p) return;
    p.points.show = p.arrows.show = p.lines.show = on;
  }

  private material(color: string): CesiumNS.Material {
    return this.C.Material.fromType("Color", { color: this.C.Color.fromCssColorString(color) });
  }

  private draw(
    layer: FeatureLayer,
    p: LayerPrimitives,
    data: LayerFeatures | null,
    loadedAt: number,
  ): void {
    const C = this.C;
    p.points.removeAll();
    p.arrows.removeAll();
    p.lines.removeAll();
    p.data = data;
    p.loadedAt = loadedAt;
    if (!data) return;
    const { style } = layer;
    const hidden = this.cockpit?.layerId === layer.id ? this.cockpit.id : null;
    for (const f of data.features) {
      const props = f.properties;
      const color = C.Color.fromCssColorString(featureColor(style, props, this.watched));
      const geometry = f.geometry;
      if (geometry.type === "Point") {
        if (f.id === hidden) continue; // the camera sits in it
        const [lon = 0, lat = 0] = geometry.coordinates;
        const position = C.Cartesian3.fromDegrees(lon, lat, featureHeight(props));
        const id: PickedFeature = { layer, id: String(f.id), properties: props, lat, lon };
        if (style.rotationProperty) {
          const heading = Number(props[style.rotationProperty] ?? 0);
          p.arrows.add({
            id,
            position,
            image: this.arrow,
            color,
            scale: Math.max(0.45, style.radius / 6),
            rotation: -C.Math.toRadians(Number.isFinite(heading) ? heading : 0),
            alignedAxis: C.Cartesian3.UNIT_Z,
            // Aircraft stay visible from far away but shrink with distance.
            scaleByDistance: new C.NearFarScalar(2e4, 1.4, 8e6, 0.5),
          });
        } else {
          p.points.add({
            id,
            position,
            color,
            pixelSize: featureSize(style, props),
            outlineColor: C.Color.fromCssColorString("#0b1220"),
            outlineWidth: 1,
          });
        }
      } else if (geometry.type === "LineString" || geometry.type === "MultiLineString") {
        const lines =
          geometry.type === "LineString" ? [geometry.coordinates] : geometry.coordinates;
        for (const line of lines) {
          if (line.length < 2) continue;
          p.lines.add({
            positions: line.map(([lon = 0, lat = 0]) => C.Cartesian3.fromDegrees(lon, lat)),
            width: 1.5,
            material: C.Material.fromType("Color", { color: color.withAlpha(0.8) }),
          });
        }
      }
    }
  }
}
