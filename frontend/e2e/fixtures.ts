import { test as base, expect, type Page, type Request } from "@playwright/test";
import type {
  Aircraft,
  GeoEvent,
  Health,
  Preferences,
  SatellitePosition,
  Watchlist,
  WatchlistDraft,
} from "../src/lib/api/types";

/** A minimal offline basemap: MapLibre only needs a valid style to fire `load`. */
const OFFLINE_STYLE = {
  version: 8,
  sources: {},
  layers: [{ id: "background", type: "background", paint: { "background-color": "#101010" } }],
};

const CAPABILITY_DISABLED = (capability: string) => ({
  status: 503,
  json: { error: "capability_disabled", capability },
});

export interface ApiScenario {
  aircraft?: Aircraft[];
  military?: Aircraft[];
  satellites?: SatellitePosition[];
  earthquakes?: GeoEvent[];
  preferences?: Preferences | "error";
  health?: Health | "error";
  /** A configured model makes the assistant available. */
  assistant?: boolean;
  /** Reachable Polymarket (it is blocked from France by default). */
  predictionOpen?: boolean;
}

export class FakeApi {
  readonly requests: Request[] = [];
  watchlists: Watchlist[] = [];
  rules: Record<string, unknown>[] = [];
  channels: Record<string, unknown>[] = [];
  alertItems: Record<string, unknown>[] = [];

  constructor(private scenario: ApiScenario) {}

  set(scenario: Partial<ApiScenario>) {
    this.scenario = { ...this.scenario, ...scenario };
  }

  calls(method: string, path: string): Request[] {
    return this.requests.filter(
      (r) => r.method() === method && new URL(r.url()).pathname === `/api/v1${path}`,
    );
  }

  async install(page: Page) {
    await page.route("https://basemaps.cartocdn.com/**", (route) =>
      route.fulfill({ json: OFFLINE_STYLE }),
    );
    await page.route("**/api/v1/**", async (route) => {
      const request = route.request();
      this.requests.push(request);
      const method = request.method();
      const path = new URL(request.url()).pathname.replace("/api/v1", "");
      const s = this.scenario;

      if (path === "/aviation/aircraft") {
        return route.fulfill({ json: { count: s.aircraft?.length ?? 0, items: s.aircraft ?? [] } });
      }
      if (path === "/aviation/military") {
        return route.fulfill({ json: { count: s.military?.length ?? 0, items: s.military ?? [] } });
      }
      if (path.startsWith("/aviation/aircraft/") && path.endsWith("/track")) {
        const icao24 = path.split("/")[3] ?? "";
        return route.fulfill({
          json: {
            icao24,
            callsign: "TRACKED",
            source: "adsblol",
            points: [0, 1, 2].map((i) => ({
              at: NOW,
              position: { lat: 48.5 + i * 0.2, lon: 2.0 + i * 0.2 },
              altitude_m: null,
              velocity_ms: null,
              heading_deg: null,
              on_ground: false,
            })),
          },
        });
      }
      if (path.startsWith("/infrastructure/facilities/")) {
        return route.fulfill({ json: { kind: path.split("/")[3], count: 0, items: [] } });
      }
      if (path === "/intel/news") {
        return route.fulfill({ json: NEWS });
      }
      if (path === "/intel/telegram") {
        const channels = (new URL(request.url()).searchParams.get("channels") ?? "").split(",");
        return route.fulfill({
          json: {
            count: 1,
            channels: channels.map((c) => ({ channel: c, posts: 1, error: null })),
            items: [
              {
                id: `${channels[0]}/42`,
                channel: channels[0],
                channel_title: "OSINT Defender",
                text: "Explosions reported near Kherson",
                published_at: NOW,
                url: `https://t.me/${channels[0]}/42`,
                views: "12K",
                has_media: true,
                countries: ["UA"],
              },
            ],
          },
        });
      }
      if (path === "/intel/cyber/exploited") {
        return route.fulfill({
          json: {
            count: 1,
            items: [
              {
                cve: "CVE-2026-65660",
                vendor: "Microsoft",
                product: "Exchange",
                name: "Exchange RCE",
                description: "Remote code execution.",
                date_added: "2026-09-25",
                due_date: "2026-10-16",
                used_in_ransomware: true,
                url: "https://nvd.nist.gov/vuln/detail/CVE-2026-65660",
              },
            ],
          },
        });
      }
      if (path === "/analysis/countries") {
        return route.fulfill({ json: SIGNALS });
      }
      if (path.startsWith("/analysis/countries/")) {
        return route.fulfill({
          json: {
            iso2: "UA",
            name: "Ukraine",
            signal: SIGNALS.items[0],
            history: [
              { at: new Date(Date.now() - 7200_000).toISOString(), score: 40, raw: {} },
              { at: new Date(Date.now() - 3600_000).toISOString(), score: 55, raw: {} },
            ],
            stories: NEWS.items.slice(0, 1),
            inputs: SIGNALS.inputs,
          },
        });
      }
      if (path === "/analysis/convergence") {
        return route.fulfill({
          json: {
            count: 1,
            inputs: [{ name: "events:fires", ok: false, error: "capability_disabled" }],
            items: [
              {
                id: "cell:16:24",
                cell: { west: 32, south: 48, east: 34, north: 50 },
                center: { lat: 49.2, lon: 33.1 },
                kinds: [
                  { kind: "reported_violence", count: 3, examples: ["Shelling"] },
                  { kind: "air_alert", count: 2, examples: ["Alert"] },
                ],
                score: 4.5,
                latest: NOW,
                country: "UA",
              },
            ],
          },
        });
      }
      if (path === "/countries") {
        return route.fulfill({
          json: [
            { iso2: "IR", name: "Iran", centroid: { lat: 32, lon: 53 }, region: "Asia" },
            {
              iso2: "US",
              name: "United States",
              centroid: { lat: 38, lon: -97 },
              region: "Americas",
            },
            { iso2: "UA", name: "Ukraine", centroid: { lat: 49, lon: 32 }, region: "Europe" },
          ],
        });
      }
      if (path === "/imagery/rasters") {
        return route.fulfill({ json: [] });
      }
      if (path === "/maritime/vessels") {
        return route.fulfill(CAPABILITY_DISABLED("maritime.vessel_positions"));
      }
      if (path === "/space/satellites") {
        const items = s.satellites ?? [];
        return route.fulfill({ json: { group: "stations", count: items.length, items } });
      }
      if (path.startsWith("/events/")) {
        const feed = path.split("/")[2];
        if (feed === "fires") return route.fulfill(CAPABILITY_DISABLED("events.fires"));
        const items = feed === "earthquakes" ? (s.earthquakes ?? []) : [];
        return route.fulfill({
          json: { feed, count: items.length, truncated: false, window_start: NOW, items },
        });
      }
      if (path === "/preferences" && method === "GET") {
        if (s.preferences === "error") return route.fulfill({ status: 500, json: {} });
        return route.fulfill({
          json: { preferences: s.preferences ?? DEFAULT_PREFERENCES, updated_at: null },
        });
      }
      if (path === "/preferences" && method === "PUT") {
        return route.fulfill({ json: { preferences: request.postDataJSON(), updated_at: "now" } });
      }
      if (path === "/watchlists" && method === "GET") {
        return route.fulfill({ json: this.watchlists });
      }
      if (path === "/watchlists" && method === "POST") {
        const list = this.toWatchlist("w1", request.postDataJSON());
        this.watchlists = [list];
        return route.fulfill({ status: 201, json: list });
      }
      if (path.startsWith("/watchlists/") && method === "PUT") {
        const list = this.toWatchlist(path.split("/")[2] ?? "w1", request.postDataJSON());
        this.watchlists = [list];
        return route.fulfill({ json: list });
      }
      if (path === "/system/health") {
        if (s.health === "error") return route.fulfill({ status: 503, json: {} });
        return route.fulfill({ json: s.health ?? HEALTHY });
      }
      if (path === "/assistant/settings" && method === "GET") {
        return route.fulfill({ json: assistantSettings(s.assistant ?? false) });
      }
      if (path === "/assistant/settings" && method === "PUT") {
        const body = request.postDataJSON();
        this.set({ assistant: Boolean(body.model) });
        return route.fulfill({
          json: {
            ...assistantSettings(Boolean(body.model)),
            model: body.model,
            source: "app",
            key_set: Boolean(body.api_key),
            key_hint: body.api_key ? "…1234" : null,
          },
        });
      }
      if (path === "/assistant/models") {
        return route.fulfill({ json: ["ollama/mistral"] });
      }
      if (path === "/assistant/ask") {
        if (!s.assistant) return route.fulfill(CAPABILITY_DISABLED("llm.completion"));
        return route.fulfill({ json: ANSWER });
      }
      if (path === "/alerts/kinds") return route.fulfill({ json: [] });
      if (path === "/alerts/channels/kinds") {
        return route.fulfill({
          json: [
            { kind: "webhook", available: true, why: null },
            { kind: "discord", available: true, why: null },
            { kind: "telegram", available: true, why: null },
            { kind: "email", available: false, why: "set ARGUS_SMTP_HOST and ARGUS_SMTP_FROM" },
          ],
        });
      }
      if (path === "/alerts/rules" && method === "GET") return route.fulfill({ json: this.rules });
      if (path === "/alerts/rules" && method === "POST") {
        const rule = {
          ...request.postDataJSON(),
          id: `r${this.rules.length + 1}`,
          created_at: NOW,
          last_fired_at: null,
        };
        this.rules.push(rule);
        return route.fulfill({ status: 201, json: rule });
      }
      if (path.startsWith("/alerts/rules/") && method === "PUT") {
        const id = path.split("/")[3];
        const rule = { ...this.rules.find((r) => r.id === id), ...request.postDataJSON() };
        this.rules = this.rules.map((r) => (r.id === id ? rule : r));
        return route.fulfill({ json: rule });
      }
      if (path === "/alerts/channels" && method === "GET")
        return route.fulfill({ json: this.channels });
      if (path === "/alerts/channels" && method === "POST") {
        const body = request.postDataJSON();
        const channel = {
          id: `c${this.channels.length + 1}`,
          name: body.name,
          kind: body.kind,
          hint: "discord.com",
        };
        this.channels.push(channel);
        return route.fulfill({ status: 201, json: channel });
      }
      if (path.startsWith("/alerts/channels/") && path.endsWith("/test")) {
        return route.fulfill({
          json: { channel_id: "c1", channel_name: "ops", ok: true, error: null },
        });
      }
      if (path === "/alerts" && method === "GET") {
        const unreadOnly = new URL(request.url()).searchParams.get("unread_only") === "true";
        const items = unreadOnly ? this.alertItems.filter((a) => !a.read) : this.alertItems;
        return route.fulfill({
          json: { unread: this.alertItems.filter((a) => !a.read).length, items },
        });
      }
      if (path === "/alerts/read") {
        const ids: string[] | null = request.postDataJSON().ids;
        this.alertItems = this.alertItems.map((a) =>
          ids === null || ids.includes(a.id as string) ? { ...a, read: true } : a,
        );
        return route.fulfill({
          json: { unread: this.alertItems.filter((a) => !a.read).length, items: this.alertItems },
        });
      }
      if (path === "/alerts/evaluate") {
        return route.fulfill({ json: { fired: [], skipped: ["earthquakes"] } });
      }
      if (path === "/assistant/usage") {
        return route.fulfill({
          json: {
            days: 30,
            calls: 12,
            input_tokens: 9000,
            output_tokens: 1200,
            cost_usd: 0.0123,
            calls_without_cost: 0,
            by_model: [],
          },
        });
      }
      if (path === "/markets/prediction" && s.predictionOpen) {
        return route.fulfill({ json: [MARKET] });
      }
      if (path === "/assistant/analyse/prediction") {
        return route.fulfill({
          json: {
            market_id: MARKET.id,
            question: MARKET.question,
            stance: "no_conclusion",
            answer: { ...ANSWER, text: "Traffic is down but ships still transit.", ungrounded: [] },
          },
        });
      }
      if (path === "/assistant/notes/markets") {
        return route.fulfill({
          json: {
            text: "Brent crude −8.59 % on the session.",
            facts: ["Brent crude −8.59 % on the session"],
            written_by: s.assistant ? "ollama/mistral" : "template",
            generated_at: NOW,
            rejected: [],
          },
        });
      }
      if (path.startsWith("/markets/assets/")) {
        const symbol = decodeURIComponent(path.split("/")[3] ?? "");
        if (symbol === "NOPE") return route.fulfill({ status: 404, json: { error: "not_found" } });
        return route.fulfill({ json: asset(symbol) });
      }
      const finance = FINANCE[path];
      if (finance !== undefined) {
        if (finance === "blocked") {
          return route.fulfill({
            status: 503,
            json: { error: "upstream_unavailable", capability: "markets.prediction" },
          });
        }
        return route.fulfill({ json: finance });
      }
      return route.fulfill({ status: 404, json: { error: "not_found" } });
    });
  }

  private toWatchlist(id: string, draft: WatchlistDraft): Watchlist {
    return {
      id,
      name: draft.name,
      items: (draft.items ?? []).map((i) => ({
        kind: i.kind,
        value: i.value,
        label: i.label ?? null,
      })),
      created_at: NOW,
      updated_at: NOW,
    };
  }
}

export const NOW = new Date(Date.now() - 5 * 60_000).toISOString();

const source = (id: string, name: string, tier: number, ownership: string) => ({
  id,
  name,
  tier,
  ownership,
});

const component = (c: string, raw: number, points: number, max: number, mode = "absolute") => ({
  component: c,
  raw,
  points,
  max_points: max,
  rule: `rule for ${c}`,
  mode,
  baseline_mean: mode === "relative" ? 12 : null,
  evidence: [],
});

export const SIGNALS = {
  count: 2,
  inputs: [
    { name: "events:conflict", ok: true, error: null },
    { name: "news", ok: false, error: "[news] timeout" },
  ],
  method: [],
  items: [
    {
      iso2: "UA",
      name: "Ukraine",
      score: 63.3,
      has_baseline: false,
      computed_at: NOW,
      components: [
        component("reported_violence", 20.5, 33, 35),
        component("news_attention", 40, 15.3, 20),
        component("air_alerts", 12, 15, 15),
        component("internet_outages", 0, 0, 15),
        component("natural_hazards", 0, 0, 15),
      ],
    },
    {
      iso2: "IR",
      name: "Iran",
      score: 40.4,
      has_baseline: false,
      computed_at: NOW,
      components: [component("reported_violence", 8, 27.4, 35)],
    },
  ],
};

export const NEWS = {
  count: 2,
  truncated: false,
  window_start: NOW,
  sources: [
    {
      source: {
        id: "bbc",
        name: "BBC News",
        feed_url: "x",
        homepage: "x",
        category: "world",
        tier: 1,
        ownership: "public",
        country: "GB",
      },
      articles: 10,
      error: null,
    },
    {
      source: {
        id: "tass",
        name: "TASS",
        feed_url: "x",
        homepage: "x",
        category: "world",
        tier: 3,
        ownership: "state",
        country: "RU",
      },
      articles: 0,
      error: "[news:tass] timeout",
    },
  ],
  items: [
    {
      id: "s1",
      title: "Trump calls Iranian plan to reopen Strait of Hormuz not acceptable",
      url: "https://www.bbc.com/news/1",
      articles: [],
      sources: [source("bbc", "BBC News", 1, "public"), source("npr", "NPR", 1, "public")],
      first_seen: NOW,
      last_updated: NOW,
      countries: ["IR", "US"],
      category: "world",
      state_media_only: false,
    },
    {
      id: "s2",
      title: "Kremlin says talks are possible",
      url: "https://tass.com/1",
      articles: [],
      sources: [source("tass", "TASS", 3, "state")],
      first_seen: NOW,
      last_updated: NOW,
      countries: [],
      category: "world",
      state_media_only: true,
    },
  ],
};

export const DEFAULT_PREFERENCES: Preferences = {
  schema_version: 1,
  enabled_layers: null,
  viewport: null,
  projection: null,
  telegram_channels: null,
};

export const HEALTHY: Health = { status: "ok", version: "test", sources: [] };

export function aircraft(icao24: string, lat: number, lon: number): Aircraft {
  return {
    icao24,
    callsign: `TEST${icao24.slice(0, 2)}`,
    registration: null,
    type_code: "A320",
    squawk: null,
    origin_country: "France",
    position: { lat, lon },
    altitude_m: 10_000,
    velocity_ms: 230,
    heading_deg: 45,
    vertical_rate_ms: 0,
    on_ground: false,
    last_contact: NOW,
    source: "opensky",
  };
}

export function earthquake(id: string, lat: number, lon: number, magnitude: number): GeoEvent {
  return {
    id: `usgs:${id}`,
    category: "earthquake",
    title: `M ${magnitude} - somewhere`,
    position: { lat, lon },
    occurred_at: NOW,
    severity: (magnitude - 2) / 6,
    magnitude,
    magnitude_unit: "mw",
    url: "https://earthquake.usgs.gov/x",
    source: "usgs",
    details: { depth_km: 10 },
  };
}

export const test = base.extend<{ api: FakeApi }>({
  // `auto`: installed for every test, even one that does not ask for `api`,
  // so no end-to-end test can ever reach a real backend or basemap.
  api: [
    async ({ page }, use) => {
      const api = new FakeApi({});
      await api.install(page);
      await use(api);
    },
    { auto: true },
  ],
});

export { expect };

const IN_TWO_HOURS = new Date(Date.now() + 2 * 3_600_000).toISOString();

export const HORMUZ = {
  id: "chokepoint6",
  name: "Strait of Hormuz",
  position: { lat: 26.6, lon: 56.3 },
  latest_date: "2026-09-20",
  last_7d_avg: 4.3,
  prior_90d_avg: 15.3,
  last_year_avg: 116,
  change_vs_90d_pct: -71.9,
  change_vs_last_year_pct: -96.3,
  tanker_share_pct: 40,
  daily: [],
  source: "portwatch",
};

/** Finance endpoints by path; "blocked" mimics Polymarket from France. */
const FINANCE: Record<string, unknown> = {
  "/markets/quotes": {
    count: 1,
    items: [
      {
        instrument: {
          symbol: "BZ=F",
          name: "Brent crude",
          asset_class: "commodity",
          unit: "USD/bbl",
        },
        price: 97.44,
        previous_close: 106.6,
        change: -9.16,
        change_pct: -8.59,
        currency: "USD",
        as_of: NOW,
        delayed: true,
        history: [100, 104, 106.6, 97.44],
        source: "yahoo",
      },
    ],
    missing: [{ key: "^N225", error: "upstream timeout" }],
  },
  "/markets/crypto": [
    {
      id: "bitcoin",
      symbol: "BTC",
      name: "Bitcoin",
      price_usd: 64250,
      change_24h_pct: 1.2,
      change_7d_pct: null,
      market_cap_usd: 1.27e12,
      volume_24h_usd: null,
      updated_at: NOW,
      source: "coingecko",
    },
  ],
  "/markets/funding": {
    count: 1,
    items: [
      {
        symbol: "BTC",
        exchange: "binance",
        rate: 0.0001,
        annualized_pct: 10.95,
        mark_price: null,
        next_funding_at: null,
      },
    ],
    missing: [],
  },
  "/markets/prediction": "blocked",
  "/macro/sentiment": [
    {
      id: "crypto",
      name: "Crypto Fear & Greed",
      latest: { at: NOW, value: 70, label: "Greed" },
      history: [],
      source: "alternative.me",
    },
  ],
  "/macro/yield-curve": {
    date: "2026-09-25",
    points: [
      { tenor: "2 Yr", years: 2, rate_pct: 4.1 },
      { tenor: "10 Yr", years: 10, rate_pct: 3.9 },
    ],
    previous: [],
    inverted_2y_10y: true,
    source: "treasury",
  },
  "/macro/calendar": [
    {
      title: "Non-Farm Employment Change",
      currency: "USD",
      at: IN_TWO_HOURS,
      impact: "high",
      forecast: "150K",
      previous: "142K",
    },
  ],
  "/maritime/chokepoints": [HORMUZ],
  "/markets/liquidations": {
    count: 1,
    items: [
      {
        symbol: "BTC",
        exchange: "okx",
        count: 100,
        since: NOW,
        until: NOW,
        long_usd: 848_000,
        short_usd: 489_000,
        largest: [],
        note: "The last 100 liquidations of OKX's BTC-USDT perpetual only.",
      },
    ],
    missing: [],
  },
  "/macro/energy-stocks": {
    count: 1,
    items: [
      {
        id: "spr",
        name: "Strategic Petroleum Reserve",
        unit: "thousand bbl",
        latest: { period: "2026-09-18", value: 284552 },
        week_change: -405,
        five_year_avg: 437_000,
        vs_five_year_pct: -34.91,
        five_year_min: 350_000,
        five_year_max: 600_000,
        history: [],
        source: "eia",
      },
    ],
    missing: [{ key: "natural_gas", error: "HTTP 429" }],
  },
  "/system/capabilities": {
    "events.earthquakes": ["usgs"],
    "aviation.aircraft_states": ["adsblol"],
  },
};

/** 120 daily bars rising from 80 to 104, with a resistance the reading reports. */
function asset(symbol: string) {
  const start = Date.parse("2026-05-01T00:00:00Z");
  const candles = Array.from({ length: 120 }, (_, i) => {
    const close = 80 + i * 0.2;
    return {
      day: new Date(start + i * 86_400_000).toISOString().slice(0, 10),
      open: close - 0.1,
      high: close + 0.5,
      low: close - 0.5,
      close,
      volume: null,
    };
  });
  return {
    instrument: {
      symbol,
      name: symbol === "BZ=F" ? "Brent crude" : symbol,
      asset_class: "commodity",
      unit: "USD/bbl",
    },
    currency: "USD",
    exchange: "NY Mercantile",
    range: "3mo",
    candles,
    technicals: {
      as_of: candles.at(-1)?.day,
      close: 103.8,
      sma_20: 102,
      sma_50: 99,
      sma_200: null,
      rsi_14: 71.2,
      high_52w: 104.3,
      low_52w: 79.5,
      sessions: 120,
      levels: [
        {
          kind: "resistance",
          price: 110.2,
          touches: 3,
          last_touch: "2026-03-01",
          distance_pct: 6.2,
        },
        { kind: "support", price: 95.7, touches: 2, last_touch: "2026-08-01", distance_pct: -7.8 },
      ],
      method: ["Levels: pivot highs and lows (5 sessions each side)."],
    },
    source: "yahoo",
    delayed: true,
  };
}

/** Open the layers drawer (idempotent) and return a layer's row, a toggle button. */
export async function layerRow(page: Page, label: string | RegExp) {
  const drawer = page.getByRole("complementary", { name: "Layers" });
  if (!(await drawer.isVisible())) await page.getByRole("button", { name: /^Layers · / }).click();
  return drawer.locator(".layer-row", { hasText: label });
}

/** Click where MapLibre draws a given coordinate. */
export async function clickLonLat(page: Page, lon: number, lat: number) {
  await page.waitForFunction(() => window.__argusMap?.loaded());
  const point = await page.evaluate(
    ([x, y]) => {
      const map = window.__argusMap;
      if (!map) throw new Error("map not exposed");
      const p = map.project([x as number, y as number]);
      const rect = map.getCanvas().getBoundingClientRect();
      return { x: rect.left + p.x, y: rect.top + p.y };
    },
    [lon, lat],
  );
  await page.mouse.click(point.x, point.y);
}

function assistantSettings(on: boolean) {
  return {
    model: on ? "ollama/mistral" : null,
    api_base: on ? "http://host.docker.internal:11434" : null,
    key_set: false,
    key_hint: null,
    source: on ? "app" : "none",
    fallbacks: [],
    available: on,
  };
}

export const ANSWER = {
  text: "Brent is down 8.59 % at 97.44; one report puts it at 91.",
  conclusive: false,
  steps: [
    { tool: "quotes", args: {}, ok: true, summary: "22 items" },
    { tool: "events", args: { feed: "conflict", lat: 15, lon: 42 }, ok: true, summary: "3 items" },
  ],
  sources: ["Yahoo Finance (delayed)", "GDELT (unverified)"],
  ungrounded: ["91"],
  provider: "llm",
  model: "ollama/mistral",
  elapsed_s: 4.2,
  structured: true,
  focus: { lat: 15, lon: 42, zoom: 6, country: null, layers: ["conflict"] },
  stance: null,
};

export const MARKET = {
  id: "m1",
  question: "Shipping through Hormuz disrupted before 31 Dec?",
  event_title: "Hormuz",
  outcomes: [
    { label: "Yes", probability: 0.18 },
    { label: "No", probability: 0.82 },
  ],
  one_day_change: null,
  volume_usd: null,
  volume_24h_usd: 2_400_000,
  end_date: null,
  url: "https://polymarket.com/event/x",
  source: "polymarket",
};

export const QUAKE_ALERT = {
  id: "a1",
  key: "eq:1",
  rule_id: "r1",
  rule_name: "Big quakes",
  at: NOW,
  title: "M 6.4 · Hualien, Taiwan",
  detail: "",
  severity: "critical",
  source: "USGS",
  url: null,
  lat: 23.9,
  lon: 121.6,
  layer: "earthquakes",
  unverified: false,
  read: false,
  deliveries: [{ channel_id: "c1", channel_name: "ops", ok: false, error: "[discord] HTTP 404" }],
};
