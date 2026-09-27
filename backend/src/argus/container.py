"""
Composition root.

The only module that knows which concrete adapters exist. Everything else
receives its collaborators through constructors, which is what lets tests
build a container with stub fetchers, an in-memory database and no network.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Protocol

from argus.adapters.adsblol import (
    AdsbLolAircraftFetcher,
    AdsbLolMilitaryFetcher,
    AdsbLolTraceFetcher,
)
from argus.adapters.aisstream import AisStreamRelay, VesselStore, VesselStoreFetcher
from argus.adapters.celestrak import CelestrakElementsFetcher
from argus.adapters.cisa_kev import CisaKevFetcher
from argus.adapters.eonet import EonetEventFetcher
from argus.adapters.finance.crypto import (
    BinanceFundingFetcher,
    CoinGeckoMarketsFetcher,
    OkxFundingFetcher,
    OkxLiquidationFetcher,
)
from argus.adapters.finance.eia import EiaSeriesFetcher
from argus.adapters.finance.macro import (
    CryptoFearGreedFetcher,
    ForexFactoryCalendarFetcher,
    TreasuryYieldFetcher,
)
from argus.adapters.finance.openbb import OpenBBQuoteFetcher, openbb_history_loader
from argus.adapters.finance.polymarket import PolymarketFetcher
from argus.adapters.finance.portwatch import PortWatchFetcher
from argus.adapters.finance.yahoo import YahooHistoryFetcher, YahooQuoteFetcher
from argus.adapters.firms import FirmsFireFetcher
from argus.adapters.gdacs import GdacsEventFetcher
from argus.adapters.gdelt import GdeltConflictFetcher
from argus.adapters.ioda import IodaOutageFetcher
from argus.adapters.launchlibrary import LaunchLibraryFetcher
from argus.adapters.llm.embeddings import LiteLLMEmbedder
from argus.adapters.llm.litellm import LiteLLMFetcher
from argus.adapters.notify.channels import Dispatcher, HttpNotifier, SmtpNotifier
from argus.adapters.opensky import OpenSkyAircraftFetcher, OpenSkyAuth, OpenSkyTrackFetcher
from argus.adapters.overpass import MIRRORS, OverpassFacilityFetcher
from argus.adapters.rainviewer import RainViewerRadarFetcher
from argus.adapters.rss import RssFeedReader
from argus.adapters.telegeography import TeleGeographyCableFetcher
from argus.adapters.telegram import TelegramPreviewReader
from argus.adapters.ukraine_alerts import UkraineAlertsFetcher
from argus.adapters.usgs import UsgsEarthquakeFetcher
from argus.config import Settings
from argus.domain.aviation import (
    AIRCRAFT_STATES,
    AIRCRAFT_TRACK,
    MILITARY_AIRCRAFT,
    AircraftQuery,
    AircraftTrack,
)
from argus.domain.chokepoints import CHOKEPOINT_TRAFFIC
from argus.domain.convergence import Convergence, SignalKind, SignalPoint
from argus.domain.cyber import EXPLOITED_VULNERABILITIES
from argus.domain.energy import ENERGY_SERIES
from argus.domain.events import (
    AIR_ALERTS,
    CONFLICT,
    DISASTER_ALERTS,
    EARTHQUAKES,
    FIRES,
    INTERNET_OUTAGES,
    LAUNCHES,
    NATURAL_EVENTS,
    EventFeed,
    GeoEvent,
)
from argus.domain.imagery import WEATHER_RADAR
from argus.domain.infrastructure import FACILITIES, SUBMARINE_CABLES
from argus.domain.llm import LLM_COMPLETION, LlmConfig
from argus.domain.macro import ECONOMIC_CALENDAR, SENTIMENT, YIELD_CURVE
from argus.domain.maritime import VESSEL_POSITIONS, ShipCategory, VesselQuery
from argus.domain.markets import (
    CRYPTO_MARKETS,
    FUNDING_RATES,
    LIQUIDATIONS,
    PREDICTION_MARKETS,
    PRICE_HISTORY,
    QUOTE,
    Quote,
)
from argus.domain.news import Story
from argus.domain.news_sources import DEFAULT_SOURCES
from argus.domain.signal_index import CountrySignal
from argus.domain.space import ORBITAL_ELEMENTS
from argus.domain.telegram import TelegramPost
from argus.infra.cache import CACHE_SCHEMA_VERSION, Cache, InMemoryTTLCache, RedisCache
from argus.infra.clock import SystemWallClock
from argus.infra.db import Database
from argus.infra.db.repositories import (
    SqlAlertRepository,
    SqlLlmSettingsRepository,
    SqlPreferencesRepository,
    SqlSignalHistoryRepository,
    SqlUsageRepository,
    SqlWatchlistRepository,
)
from argus.infra.health import HealthRegistry
from argus.infra.http import HttpClient, HttpxClient
from argus.infra.metrics import Metrics
from argus.providers.errors import AllProvidersFailedError, NoProviderError, ProviderError
from argus.providers.observers import HealthObserver, MetricsObserver
from argus.providers.registry import ProviderRegistry
from argus.services.alerts import AlertLoop, AlertsService
from argus.services.analysis import EVENT_LIMIT, AnalysisService
from argus.services.assistant.agent import AssistantService
from argus.services.assistant.notes import NotesService
from argus.services.assistant.prediction import PredictionAnalyst
from argus.services.assistant.search import SearchService
from argus.services.assistant.settings import AssistantSettingsService
from argus.services.assistant.tools import Toolbox
from argus.services.aviation import AviationService
from argus.services.cyber import CyberService
from argus.services.events import EventsService
from argus.services.finance import FinanceService
from argus.services.imagery import ImageryService
from argus.services.infrastructure import InfrastructureService
from argus.services.maritime import MaritimeService
from argus.services.news import NewsService
from argus.services.preferences import PreferencesService
from argus.services.snapshotter import SignalSnapshotter
from argus.services.space import SpaceService
from argus.services.telegram import TelegramService
from argus.services.watchlists import WatchlistService

logger = logging.getLogger(__name__)

ReadinessCheck = Callable[[], Awaitable[None]]


class BackgroundService(Protocol):
    """Long-running task started and stopped with the application."""

    name: str

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


@dataclass(slots=True)
class Container:
    settings: Settings
    http: HttpClient
    cache: Cache
    db: Database
    health: HealthRegistry
    metrics: Metrics
    registry: ProviderRegistry
    aviation: AviationService
    events: EventsService
    space: SpaceService
    maritime: MaritimeService
    infrastructure: InfrastructureService
    imagery: ImageryService
    news: NewsService
    telegram: TelegramService
    cyber: CyberService
    analysis: AnalysisService
    finance: FinanceService
    assistant: AssistantService
    assistant_settings: AssistantSettingsService
    notes: NotesService
    search: SearchService
    prediction: PredictionAnalyst
    alerts: AlertsService
    watchlists: WatchlistService
    preferences: PreferencesService
    # Dependencies the app cannot serve without; probed by /system/ready.
    readiness: dict[str, ReadinessCheck] = field(default_factory=dict)
    background: list[BackgroundService] = field(default_factory=list)

    async def start(self) -> None:
        for service in self.background:
            await service.start()

    async def aclose(self) -> None:
        await asyncio.gather(*(s.stop() for s in self.background))
        await self.http.aclose()
        await self.cache.aclose()
        await self.db.aclose()


def _register_providers(
    settings: Settings,
    registry: ProviderRegistry,
    http: HttpClient,
    cache: Cache,
    health: HealthRegistry,
) -> list[BackgroundService]:
    """Every upstream integration, in one place. Returns background services to run."""
    if settings.opensky_enabled:
        auth = (
            OpenSkyAuth(
                http, settings.opensky_client_id, settings.opensky_client_secret.get_secret_value()
            )
            if settings.opensky_client_id and settings.opensky_client_secret
            else None
        )
        registry.register(
            AIRCRAFT_STATES,
            OpenSkyAircraftFetcher(http, settings.opensky_base_url, auth),
            priority=10,
        )
        registry.register(
            AIRCRAFT_TRACK, OpenSkyTrackFetcher(http, settings.opensky_base_url, auth), priority=20
        )
    if settings.adsblol_enabled:
        registry.register(
            AIRCRAFT_STATES, AdsbLolAircraftFetcher(http, settings.adsblol_base_url), priority=20
        )
        registry.register(
            MILITARY_AIRCRAFT, AdsbLolMilitaryFetcher(http, settings.adsblol_base_url), priority=10
        )
        # Full-day traces with speeds: richer than OpenSky's, so tried first.
        registry.register(AIRCRAFT_TRACK, AdsbLolTraceFetcher(http), priority=10)

    if settings.usgs_enabled:
        registry.register(EARTHQUAKES, UsgsEarthquakeFetcher(http), priority=10)
    if settings.eonet_enabled:
        registry.register(NATURAL_EVENTS, EonetEventFetcher(http), priority=10)
    if settings.gdacs_enabled:
        registry.register(DISASTER_ALERTS, GdacsEventFetcher(http), priority=10)
    if settings.gdelt_enabled:
        registry.register(CONFLICT, GdeltConflictFetcher(http, cache), priority=10)
    if settings.ukraine_alerts_enabled:
        registry.register(AIR_ALERTS, UkraineAlertsFetcher(http), priority=10)
    if settings.launchlibrary_enabled:
        token = settings.launchlibrary_token
        registry.register(
            LAUNCHES,
            LaunchLibraryFetcher(http, token.get_secret_value() if token else None),
            priority=10,
        )
    if settings.firms_map_key:
        registry.register(
            FIRES, FirmsFireFetcher(http, settings.firms_map_key.get_secret_value()), priority=10
        )

    if settings.celestrak_enabled:
        registry.register(ORBITAL_ELEMENTS, CelestrakElementsFetcher(http), priority=10)

    if settings.cisa_kev_enabled:
        registry.register(EXPLOITED_VULNERABILITIES, CisaKevFetcher(http), priority=10)
    if settings.ioda_enabled:
        registry.register(INTERNET_OUTAGES, IodaOutageFetcher(http), priority=10)

    _register_finance(settings, registry, http)

    if settings.overpass_enabled:
        for priority, (name, url) in enumerate(MIRRORS.items(), start=1):
            registry.register(
                FACILITIES, OverpassFacilityFetcher(http, url, name), priority=priority * 10
            )
    if settings.telegeography_enabled:
        registry.register(SUBMARINE_CABLES, TeleGeographyCableFetcher(http), priority=10)
    if settings.rainviewer_enabled:
        registry.register(WEATHER_RADAR, RainViewerRadarFetcher(http), priority=10)

    background: list[BackgroundService] = []
    if settings.aisstream_api_key:
        store = VesselStore(max_age=timedelta(seconds=settings.vessel_max_age_s))
        relay = AisStreamRelay(
            settings.aisstream_api_key.get_secret_value(),
            store,
            health=health,
            bounding_boxes=settings.aisstream_bounding_boxes,
        )
        registry.register(VESSEL_POSITIONS, VesselStoreFetcher(store, relay), priority=10)
        background.append(relay)
    return background


def _register_finance(settings: Settings, registry: ProviderRegistry, http: HttpClient) -> None:
    if settings.yahoo_enabled:
        registry.register(QUOTE, YahooQuoteFetcher(http), priority=10)
        registry.register(PRICE_HISTORY, YahooHistoryFetcher(http), priority=10)
    if settings.openbb_enabled:
        try:
            registry.register(QUOTE, OpenBBQuoteFetcher(openbb_history_loader()), priority=20)
        except ImportError:
            logger.warning("ARGUS_OPENBB_ENABLED is set but openbb is not installed")
    if settings.coingecko_enabled:
        registry.register(CRYPTO_MARKETS, CoinGeckoMarketsFetcher(http), priority=10)
    if settings.funding_enabled:
        registry.register(FUNDING_RATES, BinanceFundingFetcher(http), priority=10)
        registry.register(FUNDING_RATES, OkxFundingFetcher(http), priority=20)
    if settings.liquidations_enabled:
        registry.register(LIQUIDATIONS, OkxLiquidationFetcher(http), priority=10)
    if settings.eia_enabled:
        key = settings.eia_api_key.get_secret_value() if settings.eia_api_key else "DEMO_KEY"
        registry.register(ENERGY_SERIES, EiaSeriesFetcher(http, key), priority=10)
    if settings.polymarket_enabled:
        registry.register(PREDICTION_MARKETS, PolymarketFetcher(http), priority=10)
    if settings.macro_enabled:
        registry.register(SENTIMENT, CryptoFearGreedFetcher(http), priority=10)
        registry.register(YIELD_CURVE, TreasuryYieldFetcher(http), priority=10)
        registry.register(ECONOMIC_CALENDAR, ForexFactoryCalendarFetcher(http), priority=10)
    if settings.portwatch_enabled:
        registry.register(CHOKEPOINT_TRAFFIC, PortWatchFetcher(http), priority=10)


class _AlertFeeds:
    """What alert rules read, from the real services."""

    def __init__(
        self,
        events: EventsService,
        news: NewsService,
        finance: FinanceService,
        analysis: AnalysisService,
        aviation: AviationService,
        notes: NotesService,
    ) -> None:
        self._events, self._news, self._finance = events, news, finance
        self._analysis, self._aviation, self._notes = analysis, aviation, notes

    async def earthquakes(self, hours: float) -> list[GeoEvent]:
        page = await self._events.events(
            EventFeed.EARTHQUAKES, window=timedelta(hours=hours), bbox=None, limit=EVENT_LIMIT
        )
        return page.items

    async def disasters(self, hours: float) -> list[GeoEvent]:
        page = await self._events.events(
            EventFeed.DISASTER_ALERTS, window=timedelta(hours=hours), bbox=None, limit=EVENT_LIMIT
        )
        return page.items

    async def stories(self, hours: float) -> list[Story]:
        return (await self._news.stories(window=timedelta(hours=hours), limit=500)).items

    async def quotes(self) -> list[Quote]:
        return (await self._finance.quotes()).items

    async def signals(self) -> list[CountrySignal]:
        return (await self._analysis.country_signals()).items

    async def convergences(self) -> list[Convergence]:
        return (await self._analysis.convergence()).items

    async def track(self, icao24: str) -> AircraftTrack | None:
        try:
            return await self._aviation.track(icao24)
        except (ProviderError, NoProviderError, AllProvidersFailedError):
            return None

    async def digest(self, owner: str) -> tuple[str, list[str]]:
        extra: list[str] = []
        try:
            top = (await self._analysis.country_signals()).items[:3]
            extra += [f"{c.name} signal index {c.score:.0f}" for c in top]
        except (NoProviderError, AllProvidersFailedError):
            pass
        note = await self._notes.digest(owner, extra)
        return note.text, note.facts


class _RecentStories:
    """News stories as the search corpus."""

    def __init__(self, news: NewsService) -> None:
        self._news = news

    async def recent(self, hours: float, limit: int) -> list[Story]:
        return (await self._news.stories(window=timedelta(hours=hours), limit=limit)).items


class _OwnerPosts:
    """The owner's own Telegram channels (from their preferences) as the search corpus."""

    def __init__(self, telegram: TelegramService, preferences: PreferencesService) -> None:
        self._telegram = telegram
        self._preferences = preferences

    async def recent(self, owner: str, limit: int) -> list[TelegramPost]:
        channels: list[str] = list(
            (await self._preferences.get(owner)).preferences.telegram_channels or []
        )
        if not channels:
            return []
        return (await self._telegram.posts(channels, limit)).items


def _default_llm(settings: Settings) -> LlmConfig | None:
    if not settings.llm_model:
        return None
    return LlmConfig(
        model=settings.llm_model,
        api_key=settings.llm_api_key.get_secret_value() if settings.llm_api_key else None,
        api_base=settings.llm_api_base,
        embedding_model=settings.embedding_model,
    )


def _register_llm(
    settings: Settings, registry: ProviderRegistry, llm_settings: AssistantSettingsService
) -> None:
    """The owner's model first, then the environment's fallbacks, in order."""
    if not settings.assistant_enabled:
        return
    registry.register(
        LLM_COMPLETION, LiteLLMFetcher(llm_settings.config, timeout_s=settings.llm_timeout_s)
    )
    for i, model in enumerate(settings.llm_fallback_models, start=1):
        config = LlmConfig(model=model)

        async def fixed(owner: str, config: LlmConfig = config) -> LlmConfig:
            return config

        registry.register(
            LLM_COMPLETION,
            LiteLLMFetcher(fixed, timeout_s=settings.llm_timeout_s, name=f"llm-fallback-{i}"),
            priority=100 + i,
        )


def _analysis(
    aviation: AviationService,
    events: EventsService,
    maritime: MaritimeService,
    news: NewsService,
    db: Database,
    cache: Cache,
) -> AnalysisService:
    """Wire the analysis' narrow inputs to the real services."""

    async def load_events(feed: EventFeed, window: timedelta) -> list[GeoEvent]:
        return (await events.events(feed, window=window, bbox=None, limit=EVENT_LIMIT)).items

    async def load_stories(window: timedelta, country: str | None) -> list[Story]:
        return (await news.stories(window=window, limit=500, country=country)).items

    async def military_aircraft() -> list[SignalPoint]:
        return [
            SignalPoint(
                SignalKind.MILITARY_AIRCRAFT,
                f"aircraft:{a.icao24}",
                a.callsign or a.type_code or a.icao24,
                a.position,
                a.last_contact,
            )
            for a in await aviation.military(AircraftQuery())
        ]

    async def military_vessels() -> list[SignalPoint]:
        page = await maritime.vessels(VesselQuery(), limit=100_000)
        return [
            SignalPoint(
                SignalKind.MILITARY_VESSEL,
                f"vessel:{v.mmsi}",
                v.name or v.mmsi,
                v.position,
                v.last_seen,
            )
            for v in page.items
            if v.category is ShipCategory.MILITARY
        ]

    return AnalysisService(
        events=load_events,
        stories=load_stories,
        military_aircraft=military_aircraft,
        military_vessels=military_vessels,
        history=SqlSignalHistoryRepository(db),
        cache=cache,
    )


def build_container(
    settings: Settings, http: HttpClient | None = None, cache: Cache | None = None
) -> Container:
    http = http or HttpxClient(timeout_s=settings.http_timeout_s)
    metrics = Metrics()
    health = HealthRegistry(stale_after_s=settings.health_stale_after_s)

    if cache is None:
        cache = (
            RedisCache.from_url(
                settings.redis_url,
                namespace=f"argus:v{CACHE_SCHEMA_VERSION}",
                health=health,
                metrics=metrics,
            )
            if settings.redis_url
            else InMemoryTTLCache(max_entries=settings.cache_max_entries, metrics=metrics)
        )

    db = Database(settings.database_url)
    registry = ProviderRegistry([HealthObserver(health), MetricsObserver(metrics)])
    background = _register_providers(settings, registry, http, cache, health)

    readiness: dict[str, ReadinessCheck] = {"database": db.ping}
    if settings.redis_url:
        # Not strictly required (the cache degrades), but a misconfigured URL
        # should fail the deploy, not surface as a slow app.
        readiness["cache"] = cache.ping

    aviation = AviationService(
        registry,
        cache,
        settings.aircraft_cache_ttl_s,
        military_ttl_s=settings.military_cache_ttl_s,
    )
    events = EventsService(registry, cache)
    maritime = MaritimeService(registry)
    news = NewsService(
        RssFeedReader(http), DEFAULT_SOURCES if settings.news_enabled else (), cache, health
    )
    analysis = _analysis(aviation, events, maritime, news, db, cache)
    background.append(SignalSnapshotter(analysis))
    finance = FinanceService(registry, cache)

    llm_settings = AssistantSettingsService(
        SqlLlmSettingsRepository(db),
        _default_llm(settings),
        tuple(settings.llm_fallback_models),
        http,
    )
    _register_llm(settings, registry, llm_settings)
    clock = SystemWallClock()
    telegram = TelegramService(
        TelegramPreviewReader(http) if settings.telegram_enabled else None, cache, health
    )
    preferences = PreferencesService(SqlPreferencesRepository(db))
    usage = SqlUsageRepository(db)
    search = SearchService(
        _RecentStories(news),
        _OwnerPosts(telegram, preferences),
        LiteLLMEmbedder(llm_settings.config, timeout_s=settings.llm_timeout_s),
        clock,
        usage,
    )
    assistant = AssistantService(
        registry,
        Toolbox(
            finance=finance, analysis=analysis, news=news, events=events,
            aviation=aviation, search=search,
        ),
        llm_settings,
        clock,
        usage,
    )  # fmt: skip

    notes = NotesService(assistant, finance, clock)
    alert_repo = SqlAlertRepository(db)
    smtp = (
        SmtpNotifier(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_from,
            settings.smtp_user,
            settings.smtp_password.get_secret_value() if settings.smtp_password else None,
            settings.smtp_starttls,
        )
        if settings.smtp_host and settings.smtp_from
        else None
    )
    alerts = AlertsService(
        alert_repo,
        _AlertFeeds(events, news, finance, analysis, aviation, notes),
        Dispatcher(HttpNotifier(http), smtp),
        clock,
    )
    if settings.alerts_enabled:
        background.append(AlertLoop(alerts, alert_repo, settings.alerts_interval_s))

    return Container(
        settings=settings,
        http=http,
        cache=cache,
        db=db,
        health=health,
        metrics=metrics,
        registry=registry,
        aviation=aviation,
        events=events,
        space=SpaceService(registry, cache),
        maritime=maritime,
        infrastructure=InfrastructureService(registry, cache),
        imagery=ImageryService(registry, cache),
        news=news,
        telegram=telegram,
        cyber=CyberService(registry, cache),
        analysis=analysis,
        finance=finance,
        assistant=assistant,
        assistant_settings=llm_settings,
        notes=notes,
        alerts=alerts,
        watchlists=WatchlistService(SqlWatchlistRepository(db)),
        preferences=preferences,
        search=search,
        prediction=PredictionAnalyst(assistant, finance),
        readiness=readiness,
        background=background,
    )
