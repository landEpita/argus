"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AssistantPanel, type Question } from "@/components/assistant/AssistantPanel";
import { Inspector } from "@/components/map/Inspector";
import { LayersDrawer } from "@/components/map/LayersDrawer";
import { MapFooter } from "@/components/map/MapFooter";
import { RegionBar } from "@/components/map/RegionBar";
import { RightNowPanel } from "@/components/map/RightNowPanel";
import { MarketsPage } from "@/components/markets/MarketsPage";
import { CountriesPage } from "@/components/pages/CountriesPage";
import { SourcesPage } from "@/components/pages/SourcesPage";
import { type Presence, WatchPage } from "@/components/pages/WatchPage";
import { CommandPalette } from "@/components/shell/CommandPalette";
import { TopBar } from "@/components/shell/TopBar";
import { useFeed } from "@/components/shell/useFeed";
import { useHashRoute } from "@/components/shell/useHashRoute";
import { useNow } from "@/components/shell/useNow";
import { contextOf } from "@/features/assistant/chat";
import { CountryDirectory, EMPTY_DIRECTORY } from "@/features/intel/countries";
import { layerRegistry } from "@/features/map/layers";
import { trackToFeatures } from "@/features/map/layers/aircraft";
import { watchKey } from "@/features/map/layers/features";
import { isRasterData } from "@/features/map/layers/types";
import { MapCanvas, type MapController, type Selection } from "@/features/map/MapCanvas";
import { REGIONS } from "@/features/map/regions";
import type { Projection } from "@/features/map/renderer";
import type { LayerUpdate } from "@/features/map/scheduler";
import type { Situation } from "@/features/map/situations";
import { type PreferencesStore, resolveEnabledLayers } from "@/features/preferences/store";
import type { Command } from "@/features/shell/palette";
import { SPACE_LABELS, SPACES } from "@/features/shell/space";
import type { WatchStore } from "@/features/watch/store";
import type { ApiClient } from "@/lib/api/client";
import type { Health, MapFocus, Preferences, WatchKind } from "@/lib/api/types";

const DEFAULT_POSITION = { center: { lat: 30, lon: 20 }, zoom: 2 };
const KNOWN_LAYERS = new Set(layerRegistry.all().map((l) => l.id));
const PRESENCE_LAYERS: Record<string, readonly string[]> = {
  aircraft: ["aircraft", "military"],
  vessel: ["vessels"],
};

interface Props {
  api: ApiClient;
  store: PreferencesStore;
  watch: WatchStore;
  initial: Preferences;
}

export function Cockpit({ api, store, watch, initial }: Props) {
  const route = useHashRoute();
  const now = useNow();
  const controller = useRef<MapController | null>(null);
  const [enabled, setEnabled] = useState<Set<string>>(() =>
    resolveEnabledLayers(initial.enabled_layers, KNOWN_LAYERS, layerRegistry.defaults()),
  );
  const [states, setStates] = useState<Record<string, LayerUpdate>>({});
  const [projection, setProjection] = useState<Projection>(initial.projection ?? "mercator");
  const [channels, setChannels] = useState<string[]>(() => [...(initial.telegram_channels ?? [])]);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [tracked, setTracked] = useState<string | null>(null);
  const [watched, setWatched] = useState<ReadonlySet<string>>(() => watch.watched());
  const [region, setRegion] = useState<string | null>(null);
  const [focused, setFocused] = useState<string | null>(null);
  const [leftOpen, setLeftOpen] = useState(true);
  const [layersOpen, setLayersOpen] = useState(false);
  const [palette, setPalette] = useState(false);
  const [countries, setCountries] = useState<CountryDirectory>(EMPTY_DIRECTORY);
  const [instruments, setInstruments] = useState<[string, string][]>([]);
  const [askAvailable, setAskAvailable] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [question, setQuestion] = useState<Question | null>(null);
  const initialEnabled = useRef(enabled);
  const initialProjection = useRef(projection);
  const initialPosition = useRef(initial.viewport ?? DEFAULT_POSITION);
  const initialWatched = useRef([...watch.watched()]);

  const loadHealth = useMemo(() => (s: AbortSignal) => api.health(s), [api]);
  const health = useFeed<Health>(loadHealth, 30_000);
  const unreachable = health.error != null;

  useEffect(() => {
    const c = new AbortController();
    api.countries(c.signal).then(
      (list) => setCountries(new CountryDirectory(list)),
      () => {}, // names fall back to ISO codes
    );
    return () => c.abort();
  }, [api]);

  useEffect(() => {
    const c = new AbortController();
    api.assistantSettings(c.signal).then(
      (s) => setAskAvailable(s.available),
      () => setAskAvailable(false),
    );
    return () => c.abort();
  }, [api]);

  const ask = useCallback(
    (text: string, context?: Question["context"]) => {
      if (!askAvailable) {
        route.go("sources");
        return;
      }
      setAssistantOpen(true);
      setQuestion((q) => ({ text, context, id: (q?.id ?? 0) + 1 }));
    },
    [askAvailable, route],
  );

  // Instruments for the palette: whatever the quote board carries, fetched on first open.
  useEffect(() => {
    if (!palette || instruments.length) return;
    const c = new AbortController();
    api.quotes(c.signal).then(
      (board) => setInstruments(board.items.map((q) => [q.instrument.symbol, q.instrument.name])),
      () => {},
    );
    return () => c.abort();
  }, [api, palette, instruments.length]);

  useEffect(
    () =>
      watch.subscribe((keys) => {
        setWatched(keys);
        controller.current?.setWatched([...keys]);
      }),
    [watch],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((open) => !open);
      } else if (e.key === "Escape") {
        setPalette(false);
        setLayersOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const setLayer = useCallback(
    (id: string, on: boolean) => {
      setEnabled((prev) => {
        if (prev.has(id) === on) return prev;
        const next = new Set(prev);
        if (on) next.add(id);
        else next.delete(id);
        store.update({ enabled_layers: [...next].sort() });
        return next;
      });
      if (on) controller.current?.enable(id);
      else controller.current?.disable(id);
    },
    [store],
  );
  const toggleLayer = useCallback(
    (id: string) => setLayer(id, !enabled.has(id)),
    [enabled, setLayer],
  );

  const changeProjection = useCallback(
    (next: Projection) => {
      setProjection(next);
      store.update({ projection: next });
      controller.current?.setProjection(next);
    },
    [store],
  );

  const focusPoint = useCallback(
    (lat: number, lon: number, layer?: string, zoom = 6) => {
      route.go("map");
      if (layer) setLayer(layer, true);
      setRegion(null);
      controller.current?.flyTo(lat, lon, zoom);
    },
    [route, setLayer],
  );

  const focusCountry = useCallback(
    (iso2: string, layer?: string) => {
      const c = countries.get(iso2);
      if (c) focusPoint(c.centroid.lat, c.centroid.lon, layer, 4);
    },
    [countries, focusPoint],
  );

  /** An answer's focus: only known layers, then the point or the country. */
  const applyFocus = useCallback(
    (focus: MapFocus) => {
      for (const id of focus.layers) if (KNOWN_LAYERS.has(id)) setLayer(id, true);
      if (focus.lat !== null && focus.lon !== null) {
        focusPoint(focus.lat, focus.lon, undefined, focus.zoom ?? 6);
      } else if (focus.country) {
        focusCountry(focus.country);
      } else {
        route.go("map");
      }
    },
    [setLayer, focusPoint, focusCountry, route],
  );

  const focusSituation = useCallback(
    (s: Situation) => {
      setFocused(s.id);
      focusPoint(s.center.lat, s.center.lon, "convergence", 6);
    },
    [focusPoint],
  );

  const changeChannels = useCallback(
    (next: string[]) => {
      setChannels(next);
      store.update({ telegram_channels: next });
    },
    [store],
  );

  const toggleTrack = useCallback(async () => {
    const icao24 = selection?.properties.icao24;
    if (typeof icao24 !== "string") return;
    if (tracked === icao24) {
      setTracked(null);
      controller.current?.showTrack(null);
      return;
    }
    try {
      const track = await api.track(icao24);
      setTracked(icao24);
      controller.current?.showTrack(trackToFeatures(track));
    } catch {
      setTracked(null);
      controller.current?.showTrack(null);
    }
  }, [api, selection, tracked]);

  const presence = useCallback(
    (kind: WatchKind, value: string): Presence | null => {
      for (const id of PRESENCE_LAYERS[kind] ?? []) {
        const s = states[id];
        if (s?.status !== "ready" || isRasterData(s.data)) continue;
        const f = s.data.features.find((x) => x.properties.watch_value === value);
        if (f && f.geometry.type === "Point") {
          const [lon = 0, lat = 0] = f.geometry.coordinates;
          const alt = f.properties.altitude_m;
          const detail =
            typeof alt === "number" ? `${Math.round(alt)} m` : String(f.properties.title ?? "");
          return { lat, lon, detail };
        }
      }
      return null;
    },
    [states],
  );

  const commands = useMemo<Command[]>(() => {
    const out: Command[] = SPACES.map((s) => ({
      id: `space:${s}`,
      label: `Go to ${SPACE_LABELS[s]}`,
      kind: "Space",
      run: () => route.go(s),
    }));
    for (const r of REGIONS) {
      out.push({
        id: `region:${r.id}`,
        label: `Show ${r.label}`,
        kind: "Region",
        run: () => {
          route.go("map");
          setRegion(r.id);
          controller.current?.fitBounds(r.bounds);
        },
      });
    }
    for (const layer of layerRegistry.all()) {
      const on = enabled.has(layer.id);
      out.push({
        id: `layer:${layer.id}`,
        label: `${on ? "Hide" : "Show"} ${layer.label}`,
        kind: "Layer",
        run: () => {
          route.go("map");
          setLayer(layer.id, !on);
        },
      });
    }
    for (const [symbol, name] of instruments) {
      out.push({
        id: `asset:${symbol}`,
        label: `${name} (${symbol})`,
        kind: "Instrument",
        run: () => route.go("markets", symbol),
      });
    }
    for (const c of countries.all()) {
      out.push({
        id: `country:${c.iso2}`,
        label: c.name,
        kind: "Country",
        run: () => route.go("countries", c.iso2),
      });
    }
    return out;
  }, [route, enabled, setLayer, countries, instruments]);

  const selectionKey =
    selection && typeof selection.properties.watch_value === "string" && selection.layer.watchable
      ? watchKey(selection.layer.watchable, selection.properties.watch_value)
      : null;
  const onMap = route.space === "map";

  return (
    <div className="cockpit">
      <MapCanvas
        api={api}
        registry={layerRegistry}
        initialEnabled={initialEnabled.current}
        initialProjection={initialProjection.current}
        initialPosition={initialPosition.current}
        initialWatched={initialWatched.current}
        onReady={(c) => {
          controller.current = c;
        }}
        onUpdate={(update) => setStates((prev) => ({ ...prev, [update.layerId]: update }))}
        onSelect={setSelection}
        onMove={(position) => store.update({ viewport: position })}
      />
      <TopBar
        space={route.space}
        onSpace={(s) => route.go(s)}
        onSearch={() => setPalette(true)}
        health={health.data}
        unreachable={unreachable}
        askAvailable={askAvailable}
        onAsk={() => (askAvailable ? setAssistantOpen((o) => !o) : route.go("sources"))}
      />

      {onMap && (
        <>
          {leftOpen ? (
            <RightNowPanel
              api={api}
              countries={countries}
              channels={channels}
              onChannelsChange={changeChannels}
              focused={focused}
              onFocusSituation={focusSituation}
              onFocusCountry={(iso2) => focusCountry(iso2)}
              onOpenMarkets={() => route.go("markets")}
              onClose={() => setLeftOpen(false)}
            />
          ) : (
            <button type="button" className="reopen btn glass" onClick={() => setLeftOpen(true)}>
              Right now ›
            </button>
          )}
          {layersOpen && (
            <LayersDrawer
              registry={layerRegistry}
              enabled={enabled}
              states={states}
              now={now}
              onToggle={toggleLayer}
              onClose={() => setLayersOpen(false)}
              onKeys={() => route.go("sources")}
            />
          )}
          <RegionBar
            region={region}
            projection={projection}
            onRegion={(r) => {
              setRegion(r.id);
              controller.current?.fitBounds(r.bounds);
            }}
            onProjection={changeProjection}
          />
          <MapFooter
            registry={layerRegistry}
            enabled={enabled}
            states={states}
            now={now}
            left={leftOpen || layersOpen ? 336 : 12}
            right={(assistantOpen ? 404 : 12) + (selection ? 352 : 0)}
            onToggle={toggleLayer}
            onOpenLayers={() => setLayersOpen((o) => !o)}
          />
          {selection && (
            <Inspector
              key={`${selection.layer.id}:${String(selection.properties.title)}:${selection.lat}`}
              selection={selection}
              update={states[selection.layer.id]}
              now={now}
              onClose={() => setSelection(null)}
              right={assistantOpen ? 404 : 12}
              actions={{
                watched: selectionKey ? watched.has(selectionKey) : null,
                onWatch: () => {
                  const kind = selection.layer.watchable;
                  const value = selection.properties.watch_value;
                  if (kind && typeof value === "string") {
                    const title = selection.properties.title;
                    void watch.toggle(kind, value, typeof title === "string" ? title : null);
                  }
                },
                tracked: selection.layer.tracks
                  ? tracked !== null && tracked === selection.properties.icao24
                  : null,
                onTrack: () => void toggleTrack(),
                onAsk: () =>
                  ask(
                    `Tell me about ${String(selection.properties.title ?? "this")}.`,
                    contextOf(
                      selection.layer.label,
                      selection.properties,
                      selection.lat,
                      selection.lon,
                    ),
                  ),
              }}
            />
          )}
        </>
      )}

      {route.space === "markets" && (
        <MarketsPage
          api={api}
          symbol={route.param}
          onSymbol={(s) => route.go("markets", s)}
          onFocusPoint={(lat, lon, layer) => focusPoint(lat, lon, layer, 6)}
          canAnalyse={askAvailable}
        />
      )}
      {route.space === "countries" && (
        <CountriesPage
          api={api}
          countries={countries}
          iso2={route.param}
          followed={(iso2) => watched.has(watchKey("country", iso2))}
          onSelect={(iso2) => route.go("countries", iso2)}
          onFollow={(iso2, name) => void watch.toggle("country", iso2, name)}
          onOpenMap={(iso2) => focusCountry(iso2, "country-index")}
        />
      )}
      {route.space === "watch" && (
        <WatchPage
          api={api}
          countries={countries}
          listId={route.param}
          presence={presence}
          onSelectList={(id) => route.go("watch", id)}
          onChanged={() => void watch.load()}
          onOpenMap={(lat, lon) => focusPoint(lat, lon, undefined, 7)}
          onOpenAsset={(s) => route.go("markets", s)}
          onOpenCountry={(iso2) => route.go("countries", iso2)}
        />
      )}
      {route.space === "sources" && (
        <SourcesPage
          api={api}
          health={health.data}
          unreachable={unreachable}
          onAssistantChanged={(s) => setAskAvailable(s.available)}
        />
      )}

      {assistantOpen && (
        <AssistantPanel
          api={api}
          question={question}
          onClose={() => setAssistantOpen(false)}
          onSettings={() => route.go("sources")}
          onFocus={applyFocus}
        />
      )}
      {palette && (
        <CommandPalette
          commands={commands}
          onClose={() => setPalette(false)}
          onAsk={askAvailable ? (q) => ask(q) : undefined}
        />
      )}
    </div>
  );
}
