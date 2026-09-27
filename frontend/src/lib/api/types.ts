// Public names for the API's schemas. The shapes themselves are generated from
// the backend's OpenAPI document into schema.gen.ts (`make api-types`), so a
// backend change that breaks the frontend fails `tsc`, not the user.
import type { components } from "./schema.gen";

type Schemas = components["schemas"];

export type GeoPoint = Schemas["GeoPoint"];
export type Aircraft = Schemas["Aircraft"];
export type AircraftCollection = Schemas["AircraftCollection"];

export type Vessel = Schemas["Vessel"];
export type VesselCollection = Schemas["VesselCollection"];
export type ShipCategory = Schemas["ShipCategory"];

export type SatelliteGroup = Schemas["SatelliteGroup"];
export type SatellitePosition = Schemas["SatellitePosition"];
export type SatelliteCollection = Schemas["SatelliteCollection"];

export type EventFeed = Schemas["EventFeed"];
export type EventCategory = Schemas["EventCategory"];
export type GeoEvent = Schemas["GeoEvent"];
export type EventCollection = Schemas["EventCollection"];
export type FeedInfo = Schemas["FeedInfo"];

export type HealthStatus = Schemas["HealthStatus"];
export type SourceHealth = Schemas["SourceHealthOut"];
export type Health = Schemas["HealthOut"];

// Models used both as request and response get two schemas: "-Output" has
// every field present; "-Input" lets defaulted fields be omitted.
export type Viewport = Schemas["Viewport"];
export type Preferences = Schemas["Preferences-Output"];
export type PreferencesInput = Schemas["Preferences-Input"];
export type StoredPreferences = Schemas["StoredPreferences"];

export type WatchKind = Schemas["WatchKind"];
export type WatchItem = Schemas["WatchItem-Output"];
export type Watchlist = Schemas["Watchlist"];
export type WatchlistDraft = Schemas["WatchlistDraft"];

export type TrackPoint = Schemas["TrackPoint"];
export type AircraftTrack = Schemas["AircraftTrack"];

export type FacilityKind = Schemas["FacilityKind"];
export type Facility = Schemas["Facility"];
export type FacilityCollection = Schemas["FacilityCollection"];
export type Cable = Schemas["Cable"];
export type LandingPoint = Schemas["LandingPoint"];
export type CableNetwork = Schemas["CableNetwork"];
export type Camera = Schemas["Camera"];
export type CameraCollection = Schemas["CameraCollection"];
export type LiveChannel = Schemas["Channel"];
export type Stream = Schemas["Stream"];
export type Webcam = Schemas["Webcam"];
export type MapConfig = Schemas["MapConfigOut"];

export type RasterLayer = Schemas["RasterLayer"];

export type Ownership = Schemas["Ownership"];
export type NewsCategory = Schemas["NewsCategory"];
export type NewsSource = Schemas["NewsSource"];
export type Article = Schemas["Article"];
export type Story = Schemas["Story"];
export type StorySource = Schemas["StorySource"];
export type StoryCollection = Schemas["StoryCollection"];
export type TelegramPost = Schemas["TelegramPost"];
export type TelegramCollection = Schemas["TelegramCollection"];
export type ExploitedVulnerability = Schemas["ExploitedVulnerability"];
export type VulnerabilityCollection = Schemas["VulnerabilityCollection"];
export type CountryInfo = Schemas["CountryOut"];

export type SignalComponent = Schemas["Component"];
export type ComponentScore = Schemas["ComponentScore"];
export type CountrySignal = Schemas["CountrySignal"];
export type CountrySignalCollection = Schemas["CountrySignalCollection"];
export type CountryDetail = Schemas["CountryDetailOut"];
export type HistoryPoint = Schemas["HistoryPoint"];
export type InputStatus = Schemas["InputStatusOut"];
export type SignalKind = Schemas["SignalKind"];
export type Convergence = Schemas["Convergence"];
export type ConvergenceCollection = Schemas["ConvergenceCollection"];

export type Instrument = Schemas["Instrument"];
export type Quote = Schemas["Quote"];
export type QuoteBoard = Schemas["QuoteBoard"];
export type CryptoAsset = Schemas["CryptoAsset"];
export type FundingRate = Schemas["FundingRate"];
export type FundingBoard = Schemas["FundingBoard"];
export type PredictionMarket = Schemas["PredictionMarket"];
export type SentimentIndex = Schemas["SentimentIndex"];
export type YieldCurve = Schemas["YieldCurve"];
export type CalendarEvent = Schemas["CalendarEvent"];
export type ChokepointTraffic = Schemas["ChokepointTraffic"];
export type Candle = Schemas["Candle"];
export type HistoryRange = Schemas["HistoryRange"];
export type Technicals = Schemas["Technicals"];
export type Level = Schemas["Level"];
export type AssetDetail = Schemas["AssetOut"];
export type LiquidationSummary = Schemas["LiquidationSummary"];
export type LiquidationBoard = Schemas["LiquidationBoard"];
export type EnergyStock = Schemas["EnergyStock"];
export type EnergyBoard = Schemas["EnergyBoard"];
export type Capabilities = Record<string, string[]>;
export type AssistantSettings = Schemas["SettingsOut"];
export type AssistantSettingsInput = Schemas["SettingsIn"];
export type AssistantTest = Schemas["TestOut"];
export type AskInput = Schemas["AskIn"];
export type Answer = Schemas["AnswerOut"];
export type AnswerStep = Schemas["StepOut"];
export type MarketNote = Schemas["NoteOut"];
export type MapFocus = Schemas["FocusOut"];
export type Usage = Schemas["UsageOut"];
export type PredictionReading = Schemas["PredictionReadingOut"];
export type SearchResults = Schemas["SearchOut"];
export type AlertRule = Schemas["Rule"];
export type AlertRuleDraft = Schemas["RuleDraft"];
export type RuleKind = Schemas["RuleKind"];
export type AlertChannel = Schemas["ChannelOut"];
export type AlertChannelDraft = Schemas["ChannelDraft"];
export type ChannelKind = Schemas["ChannelKind"];
export type ChannelKindInfo = Schemas["ChannelKindOut"];
export type AlertItem = Schemas["Alert"];
export type AlertFeed = Schemas["FeedOut"];
export type Evaluation = Schemas["EvaluationOut"];
export type Delivery = Schemas["Delivery"];
export type AlertSettings = Schemas["AlertSettings-Output"];
export type AlertSettingsInput = Schemas["AlertSettings-Input"];
