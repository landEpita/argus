"""Settings, read from the environment (prefix ``ARGUS_``) or a ``.env`` file."""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARGUS_", env_file=".env", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"
    log_json: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Storage. SQLite needs no server; docker-compose points this at Postgres.
    database_url: str = "sqlite+aiosqlite:///./argus.db"
    # Unset = in-process cache. Set (redis://…) to share the cache across processes.
    redis_url: str | None = None

    http_timeout_s: float = Field(default=10.0, gt=0)
    cache_max_entries: int = Field(default=1024, ge=1)
    health_stale_after_s: float = Field(default=30 * 60, gt=0)

    # ── Aviation ──
    opensky_enabled: bool = True
    opensky_base_url: str = "https://opensky-network.org/api"
    # Optional OAuth client (free account): 4,000 credits/day instead of 400 anonymous.
    opensky_client_id: str | None = None
    opensky_client_secret: SecretStr | None = None
    adsblol_enabled: bool = True
    adsblol_base_url: str = "https://api.adsb.lol"
    aircraft_cache_ttl_s: float = Field(default=15.0, ge=0)
    # One worldwide OpenSky snapshot serves every zoomed-out view. Anonymous OpenSky allows
    # ~100 world snapshots a day (400 credits): keep this high without an OpenSky account.
    aircraft_world_ttl_s: float = Field(default=300.0, ge=10)
    military_cache_ttl_s: float = Field(default=30.0, ge=0)

    # ── Events (no key needed unless noted) ──
    usgs_enabled: bool = True
    eonet_enabled: bool = True
    gdacs_enabled: bool = True
    gdelt_enabled: bool = True
    ukraine_alerts_enabled: bool = True
    launchlibrary_enabled: bool = True
    # Optional: raises Launch Library's 15 requests/hour anonymous limit.
    launchlibrary_token: SecretStr | None = None
    # https://firms.modaps.eosdis.nasa.gov/api/map_key/ (free). Unset = fires feed disabled.
    firms_map_key: SecretStr | None = None

    # ── Space ──
    celestrak_enabled: bool = True

    # ── Intelligence feeds ──
    news_enabled: bool = True
    telegram_enabled: bool = True
    cisa_kev_enabled: bool = True
    ioda_enabled: bool = True

    # ── Finance ──
    yahoo_enabled: bool = True
    coingecko_enabled: bool = True
    funding_enabled: bool = True
    polymarket_enabled: bool = True
    macro_enabled: bool = True
    portwatch_enabled: bool = True
    liquidations_enabled: bool = True
    eia_enabled: bool = True
    # https://www.eia.gov/opendata/register.php (free). Unset = DEMO_KEY, a few calls per hour.
    eia_api_key: SecretStr | None = None
    # Optional fallback quote provider; needs `pip install argus-backend[openbb]`.
    openbb_enabled: bool = False

    # ── Assistant (any LiteLLM model: "ollama/mistral", "anthropic/claude-sonnet-5"…) ──
    # Defaults; a model saved in the app's settings wins. Unset = assistant off.
    assistant_enabled: bool = True
    # Read-only MCP server at /mcp (streamable HTTP), for Claude Desktop / Claude Code.
    mcp_enabled: bool = True
    llm_model: str | None = None
    llm_api_key: SecretStr | None = None
    # Ollama or any self-hosted endpoint, e.g. http://host.docker.internal:11434
    llm_api_base: str | None = None
    # Tried in order when the main model fails; each reads its provider's usual
    # environment variable (ANTHROPIC_API_KEY, OPENAI_API_KEY, GROQ_API_KEY…).
    llm_fallback_models: list[str] = []
    llm_timeout_s: float = 120.0
    # Semantic search (optional); uses the same key and base URL, e.g. ollama/nomic-embed-text.
    embedding_model: str | None = None

    # ── Alerts ──
    alerts_enabled: bool = True
    alerts_interval_s: float = 120.0
    # E-mail channel (any SMTP server); unset = the e-mail channel is unavailable.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str | None = None
    smtp_starttls: bool = True
    # Web Push: the VAPID key is generated once and kept in the database.
    web_push_enabled: bool = True
    web_push_subject: str = "mailto:argus@localhost"

    # ── Infrastructure & imagery ──
    overpass_enabled: bool = True
    telegeography_enabled: bool = True
    rainviewer_enabled: bool = True

    # ── Maritime ──
    # https://aisstream.io (free). Unset = vessels disabled.
    aisstream_api_key: SecretStr | None = None
    # [[[south, west], [north, east]], …]; the default is the whole world.
    aisstream_bounding_boxes: list[list[list[float]]] = Field(
        default_factory=lambda: [[[-90.0, -180.0], [90.0, 180.0]]]
    )
    vessel_max_age_s: float = Field(default=30 * 60, gt=0)
