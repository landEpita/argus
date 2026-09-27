import { type BBox, bboxToParam } from "@/lib/geo";
import type {
  AircraftCollection,
  AircraftTrack,
  AlertChannel,
  AlertChannelDraft,
  AlertFeed,
  AlertRule,
  AlertRuleDraft,
  AlertSettings,
  AlertSettingsInput,
  Answer,
  AskInput,
  AssetDetail,
  AssistantSettings,
  AssistantSettingsInput,
  AssistantTest,
  CableNetwork,
  CalendarEvent,
  CameraCollection,
  Capabilities,
  ChannelKindInfo,
  ChokepointTraffic,
  ConvergenceCollection,
  CountryDetail,
  CountryInfo,
  CountrySignalCollection,
  CryptoAsset,
  Delivery,
  EnergyBoard,
  Evaluation,
  EventCollection,
  EventFeed,
  FacilityCollection,
  FacilityKind,
  FeedInfo,
  FundingBoard,
  Health,
  HistoryRange,
  LiquidationBoard,
  MarketNote,
  NewsCategory,
  PredictionMarket,
  PredictionReading,
  PreferencesInput,
  QuoteBoard,
  RasterLayer,
  SatelliteCollection,
  SatelliteGroup,
  SearchResults,
  SentimentIndex,
  StoredPreferences,
  StoryCollection,
  TelegramCollection,
  Usage,
  VesselCollection,
  VulnerabilityCollection,
  Watchlist,
  WatchlistDraft,
  YieldCurve,
} from "./types";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: unknown,
  ) {
    super(`API request failed with HTTP ${status}`);
    this.name = "ApiError";
  }
}

export interface AircraftParams {
  bbox?: BBox;
  includeOnGround?: boolean;
}

export interface EventParams {
  bbox?: BBox;
  sinceHours?: number;
  limit?: number;
}

export interface NewsParams {
  sinceHours?: number;
  limit?: number;
  category?: NewsCategory;
  country?: string;
  q?: string;
}

export interface ApiClient {
  aircraft(params: AircraftParams, signal?: AbortSignal): Promise<AircraftCollection>;
  military(params: AircraftParams, signal?: AbortSignal): Promise<AircraftCollection>;
  track(icao24: string, signal?: AbortSignal): Promise<AircraftTrack>;
  facilities(kind: FacilityKind, bbox: BBox, signal?: AbortSignal): Promise<FacilityCollection>;
  cables(signal?: AbortSignal): Promise<CableNetwork>;
  cameras(bbox: BBox, signal?: AbortSignal): Promise<CameraCollection>;
  rasters(signal?: AbortSignal): Promise<RasterLayer[]>;
  news(params: NewsParams, signal?: AbortSignal): Promise<StoryCollection>;
  telegram(channels: readonly string[], signal?: AbortSignal): Promise<TelegramCollection>;
  exploited(days: number, signal?: AbortSignal): Promise<VulnerabilityCollection>;
  countries(signal?: AbortSignal): Promise<CountryInfo[]>;
  countrySignals(signal?: AbortSignal): Promise<CountrySignalCollection>;
  countryDetail(iso2: string, signal?: AbortSignal): Promise<CountryDetail>;
  convergence(signal?: AbortSignal): Promise<ConvergenceCollection>;
  quotes(signal?: AbortSignal): Promise<QuoteBoard>;
  crypto(limit: number, signal?: AbortSignal): Promise<CryptoAsset[]>;
  funding(symbols: readonly string[], signal?: AbortSignal): Promise<FundingBoard>;
  prediction(signal?: AbortSignal): Promise<PredictionMarket[]>;
  sentiment(signal?: AbortSignal): Promise<SentimentIndex[]>;
  yieldCurve(signal?: AbortSignal): Promise<YieldCurve>;
  calendar(impact?: "high", signal?: AbortSignal): Promise<CalendarEvent[]>;
  chokepoints(signal?: AbortSignal): Promise<ChokepointTraffic[]>;
  asset(symbol: string, range: HistoryRange, signal?: AbortSignal): Promise<AssetDetail>;
  liquidations(symbols: readonly string[], signal?: AbortSignal): Promise<LiquidationBoard>;
  energyStocks(signal?: AbortSignal): Promise<EnergyBoard>;
  capabilities(signal?: AbortSignal): Promise<Capabilities>;
  assistantSettings(signal?: AbortSignal): Promise<AssistantSettings>;
  saveAssistantSettings(body: AssistantSettingsInput): Promise<AssistantSettings>;
  testAssistant(): Promise<AssistantTest>;
  localModels(apiBase: string, signal?: AbortSignal): Promise<string[]>;
  ask(body: AskInput, signal?: AbortSignal): Promise<Answer>;
  marketNote(signal?: AbortSignal): Promise<MarketNote>;
  usage(days: number, signal?: AbortSignal): Promise<Usage>;
  analysePrediction(marketId: string, signal?: AbortSignal): Promise<PredictionReading>;
  search(q: string, signal?: AbortSignal): Promise<SearchResults>;
  alertRules(signal?: AbortSignal): Promise<AlertRule[]>;
  createAlertRule(draft: AlertRuleDraft): Promise<AlertRule>;
  updateAlertRule(id: string, draft: AlertRuleDraft): Promise<AlertRule>;
  deleteAlertRule(id: string): Promise<void>;
  alertChannels(signal?: AbortSignal): Promise<AlertChannel[]>;
  alertChannelKinds(signal?: AbortSignal): Promise<ChannelKindInfo[]>;
  createAlertChannel(draft: AlertChannelDraft): Promise<AlertChannel>;
  deleteAlertChannel(id: string): Promise<void>;
  testAlertChannel(id: string): Promise<Delivery>;
  alerts(unreadOnly?: boolean, signal?: AbortSignal): Promise<AlertFeed>;
  markAlertsRead(ids?: string[]): Promise<AlertFeed>;
  evaluateAlerts(): Promise<Evaluation>;
  alertSettings(signal?: AbortSignal): Promise<AlertSettings>;
  saveAlertSettings(body: AlertSettingsInput): Promise<AlertSettings>;
  pushKey(): Promise<{ public_key: string }>;
  vessels(params: { bbox?: BBox }, signal?: AbortSignal): Promise<VesselCollection>;
  satellites(group: SatelliteGroup, signal?: AbortSignal): Promise<SatelliteCollection>;
  feeds(signal?: AbortSignal): Promise<FeedInfo[]>;
  events(feed: EventFeed, params: EventParams, signal?: AbortSignal): Promise<EventCollection>;
  health(signal?: AbortSignal): Promise<Health>;
  preferences(signal?: AbortSignal): Promise<StoredPreferences>;
  savePreferences(preferences: PreferencesInput, signal?: AbortSignal): Promise<StoredPreferences>;
  watchlists(signal?: AbortSignal): Promise<Watchlist[]>;
  createWatchlist(draft: WatchlistDraft): Promise<Watchlist>;
  replaceWatchlist(id: string, draft: WatchlistDraft): Promise<Watchlist>;
  deleteWatchlist(id: string): Promise<void>;
}

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

type Method = "GET" | "POST" | "PUT" | "DELETE";

interface RequestOptions {
  query?: Record<string, string>;
  body?: unknown;
  signal?: AbortSignal;
}

/** `baseUrl` is empty in the browser: requests go to the same origin and Next proxies them. */
export function createApiClient(baseUrl = "", fetchImpl: FetchLike = fetch): ApiClient {
  async function request<T>(method: Method, path: string, options: RequestOptions = {}) {
    const qs = options.query ? new URLSearchParams(options.query).toString() : "";
    const headers: Record<string, string> = { Accept: "application/json" };
    if (options.body !== undefined) headers["Content-Type"] = "application/json";

    const response = await fetchImpl(`${baseUrl}/api/v1${path}${qs ? `?${qs}` : ""}`, {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new ApiError(response.status, body);
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  function aircraftQuery({ bbox, includeOnGround = false }: AircraftParams) {
    const query: Record<string, string> = { include_on_ground: String(includeOnGround) };
    if (bbox) query.bbox = bboxToParam(bbox);
    return query;
  }

  return {
    aircraft: (params, signal) =>
      request<AircraftCollection>("GET", "/aviation/aircraft", {
        query: aircraftQuery(params),
        signal,
      }),
    military: (params, signal) =>
      request<AircraftCollection>("GET", "/aviation/military", {
        query: aircraftQuery(params),
        signal,
      }),
    track: (icao24, signal) =>
      request<AircraftTrack>("GET", `/aviation/aircraft/${encodeURIComponent(icao24)}/track`, {
        signal,
      }),
    facilities: (kind, bbox, signal) =>
      request<FacilityCollection>("GET", `/infrastructure/facilities/${encodeURIComponent(kind)}`, {
        query: { bbox: bboxToParam(bbox) },
        signal,
      }),
    cables: (signal) =>
      request<CableNetwork>("GET", "/infrastructure/submarine-cables", { signal }),
    cameras: (bbox, signal) =>
      request<CameraCollection>("GET", "/cameras", { query: { bbox: bboxToParam(bbox) }, signal }),
    rasters: (signal) => request<RasterLayer[]>("GET", "/imagery/rasters", { signal }),
    news({ sinceHours, limit, category, country, q }, signal) {
      const query: Record<string, string> = {};
      if (sinceHours !== undefined) query.since_hours = String(sinceHours);
      if (limit !== undefined) query.limit = String(limit);
      if (category) query.category = category;
      if (country) query.country = country;
      if (q) query.q = q;
      return request<StoryCollection>("GET", "/intel/news", { query, signal });
    },
    telegram: (channels, signal) =>
      request<TelegramCollection>("GET", "/intel/telegram", {
        query: { channels: channels.join(",") },
        signal,
      }),
    exploited: (days, signal) =>
      request<VulnerabilityCollection>("GET", "/intel/cyber/exploited", {
        query: { days: String(days) },
        signal,
      }),
    countries: (signal) => request<CountryInfo[]>("GET", "/countries", { signal }),
    countrySignals: (signal) =>
      request<CountrySignalCollection>("GET", "/analysis/countries", { signal }),
    countryDetail: (iso2, signal) =>
      request<CountryDetail>("GET", `/analysis/countries/${encodeURIComponent(iso2)}`, { signal }),
    convergence: (signal) =>
      request<ConvergenceCollection>("GET", "/analysis/convergence", { signal }),
    quotes: (signal) => request<QuoteBoard>("GET", "/markets/quotes", { signal }),
    crypto: (limit, signal) =>
      request<CryptoAsset[]>("GET", "/markets/crypto", { query: { limit: String(limit) }, signal }),
    funding: (symbols, signal) =>
      request<FundingBoard>("GET", "/markets/funding", {
        query: { symbols: symbols.join(",") },
        signal,
      }),
    prediction: (signal) => request<PredictionMarket[]>("GET", "/markets/prediction", { signal }),
    sentiment: (signal) => request<SentimentIndex[]>("GET", "/macro/sentiment", { signal }),
    yieldCurve: (signal) => request<YieldCurve>("GET", "/macro/yield-curve", { signal }),
    calendar: (impact, signal) =>
      request<CalendarEvent[]>("GET", "/macro/calendar", {
        query: impact ? { impact } : {},
        signal,
      }),
    chokepoints: (signal) =>
      request<ChokepointTraffic[]>("GET", "/maritime/chokepoints", { signal }),
    asset: (symbol, range, signal) =>
      request<AssetDetail>("GET", `/markets/assets/${encodeURIComponent(symbol)}`, {
        query: { range },
        signal,
      }),
    liquidations: (symbols, signal) =>
      request<LiquidationBoard>("GET", "/markets/liquidations", {
        query: { symbols: symbols.join(",") },
        signal,
      }),
    energyStocks: (signal) => request<EnergyBoard>("GET", "/macro/energy-stocks", { signal }),
    capabilities: (signal) => request<Capabilities>("GET", "/system/capabilities", { signal }),
    assistantSettings: (signal) =>
      request<AssistantSettings>("GET", "/assistant/settings", { signal }),
    saveAssistantSettings: (body) =>
      request<AssistantSettings>("PUT", "/assistant/settings", { body }),
    testAssistant: () => request<AssistantTest>("POST", "/assistant/settings/test", {}),
    localModels: (apiBase, signal) =>
      request<string[]>("GET", "/assistant/models", { query: { api_base: apiBase }, signal }),
    ask: (body, signal) => request<Answer>("POST", "/assistant/ask", { body, signal }),
    marketNote: (signal) => request<MarketNote>("GET", "/assistant/notes/markets", { signal }),
    usage: (days, signal) =>
      request<Usage>("GET", "/assistant/usage", { query: { days: String(days) }, signal }),
    analysePrediction: (marketId, signal) =>
      request<PredictionReading>("POST", "/assistant/analyse/prediction", {
        body: { market_id: marketId },
        signal,
      }),
    alertRules: (signal) => request<AlertRule[]>("GET", "/alerts/rules", { signal }),
    createAlertRule: (body) => request<AlertRule>("POST", "/alerts/rules", { body }),
    updateAlertRule: (id, body) =>
      request<AlertRule>("PUT", `/alerts/rules/${encodeURIComponent(id)}`, { body }),
    deleteAlertRule: (id) => request<void>("DELETE", `/alerts/rules/${encodeURIComponent(id)}`),
    alertChannels: (signal) => request<AlertChannel[]>("GET", "/alerts/channels", { signal }),
    alertChannelKinds: (signal) =>
      request<ChannelKindInfo[]>("GET", "/alerts/channels/kinds", { signal }),
    createAlertChannel: (body) => request<AlertChannel>("POST", "/alerts/channels", { body }),
    deleteAlertChannel: (id) =>
      request<void>("DELETE", `/alerts/channels/${encodeURIComponent(id)}`),
    testAlertChannel: (id) =>
      request<Delivery>("POST", `/alerts/channels/${encodeURIComponent(id)}/test`, {}),
    alerts: (unreadOnly, signal) =>
      request<AlertFeed>("GET", "/alerts", {
        query: unreadOnly ? { unread_only: "true" } : {},
        signal,
      }),
    markAlertsRead: (ids) =>
      request<AlertFeed>("POST", "/alerts/read", { body: { ids: ids ?? null } }),
    evaluateAlerts: () => request<Evaluation>("POST", "/alerts/evaluate", {}),
    alertSettings: (signal) => request<AlertSettings>("GET", "/alerts/settings", { signal }),
    saveAlertSettings: (body) => request<AlertSettings>("PUT", "/alerts/settings", { body }),
    pushKey: () => request<{ public_key: string }>("GET", "/alerts/push/key", {}),
    search: (q, signal) =>
      request<SearchResults>("GET", "/assistant/search", { query: { q }, signal }),
    vessels: ({ bbox }, signal) =>
      request<VesselCollection>("GET", "/maritime/vessels", {
        query: bbox ? { bbox: bboxToParam(bbox) } : {},
        signal,
      }),
    satellites: (group, signal) =>
      request<SatelliteCollection>("GET", "/space/satellites", { query: { group }, signal }),
    feeds: (signal) => request<FeedInfo[]>("GET", "/events", { signal }),
    events(feed, { bbox, sinceHours, limit }, signal) {
      const query: Record<string, string> = {};
      if (bbox) query.bbox = bboxToParam(bbox);
      if (sinceHours !== undefined) query.since_hours = String(sinceHours);
      if (limit !== undefined) query.limit = String(limit);
      return request<EventCollection>("GET", `/events/${encodeURIComponent(feed)}`, {
        query,
        signal,
      });
    },
    health: (signal) => request<Health>("GET", "/system/health", { signal }),
    preferences: (signal) => request<StoredPreferences>("GET", "/preferences", { signal }),
    savePreferences: (body, signal) =>
      request<StoredPreferences>("PUT", "/preferences", { body, signal }),
    watchlists: (signal) => request<Watchlist[]>("GET", "/watchlists", { signal }),
    createWatchlist: (body) => request<Watchlist>("POST", "/watchlists", { body }),
    replaceWatchlist: (id, body) =>
      request<Watchlist>("PUT", `/watchlists/${encodeURIComponent(id)}`, { body }),
    deleteWatchlist: (id) => request<void>("DELETE", `/watchlists/${encodeURIComponent(id)}`),
  };
}
