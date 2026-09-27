"""
Which model the assistant uses, per owner.

Settings saved in the app win over the environment (``ARGUS_LLM_*``). The API
key is stored server side and never returned: callers see whether one is set
and its last four characters.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from argus.domain.llm import LlmConfig, LlmSettingsRepository, StoredLlmSettings
from argus.infra.http import HttpClient
from argus.providers.errors import ProviderError


class SettingsSource(StrEnum):
    APP = "app"
    ENVIRONMENT = "environment"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class SettingsView:
    model: str | None
    api_base: str | None
    key_set: bool
    key_hint: str | None
    source: SettingsSource
    fallbacks: tuple[str, ...]
    embedding_model: str | None = None


@dataclass(frozen=True, slots=True)
class SettingsUpdate:
    model: str | None
    api_base: str | None
    # None keeps the stored key; "" removes it.
    api_key: str | None = None
    embedding_model: str | None = None


def _hint(key: str | None) -> str | None:
    return f"…{key[-4:]}" if key and len(key) >= 8 else ("set" if key else None)


class AssistantSettingsService:
    def __init__(
        self,
        repository: LlmSettingsRepository,
        default: LlmConfig | None,
        fallbacks: tuple[str, ...] = (),
        http: HttpClient | None = None,
    ) -> None:
        self._http = http
        self._repo = repository
        self._default = default
        self._fallbacks = fallbacks
        self._cache: dict[str, LlmConfig | None] = {}

    async def config(self, owner: str) -> LlmConfig | None:
        """What to call for this owner: their saved choice, else the environment's."""
        if owner not in self._cache:
            stored = await self._repo.get(owner)
            self._cache[owner] = (
                LlmConfig(
                    model=stored.model,
                    api_key=stored.api_key,
                    api_base=stored.api_base,
                    embedding_model=stored.embedding_model,
                )
                if stored and stored.model
                else self._default
            )
        return self._cache[owner]

    async def view(self, owner: str) -> SettingsView:
        stored = await self._repo.get(owner)
        if stored and stored.model:
            return SettingsView(
                stored.model, stored.api_base, bool(stored.api_key), _hint(stored.api_key),
                SettingsSource.APP, self._fallbacks, stored.embedding_model,
            )  # fmt: skip
        if self._default:
            d = self._default
            return SettingsView(
                d.model, d.api_base, bool(d.api_key), _hint(d.api_key),
                SettingsSource.ENVIRONMENT, self._fallbacks, d.embedding_model,
            )  # fmt: skip
        return SettingsView(None, None, False, None, SettingsSource.NONE, self._fallbacks)

    async def save(self, owner: str, update: SettingsUpdate) -> SettingsView:
        stored = await self._repo.get(owner)
        key = stored.api_key if stored else None
        if update.api_key is not None:
            key = update.api_key.strip() or None
        model = update.model.strip() if update.model else None
        embedding = update.embedding_model.strip() if update.embedding_model else None
        if model:
            LlmConfig(  # validates
                model=model, api_key=key, api_base=update.api_base or None,
                embedding_model=embedding,
            )  # fmt: skip
        await self._repo.save(
            owner,
            StoredLlmSettings(
                model=model or None,
                api_key=key,
                api_base=update.api_base or None,
                embedding_model=embedding if model else None,
            ),
        )
        self._cache.pop(owner, None)
        return await self.view(owner)

    async def local_models(self, api_base: str) -> list[str]:
        """Models an Ollama server has pulled, as LiteLLM names (``ollama/<name>``)."""
        if self._http is None:
            return []
        try:
            raw = await self._http.get_json(
                f"{api_base.rstrip('/')}/api/tags", provider="ollama", timeout_s=3
            )
        except ProviderError:
            return []
        models = raw.get("models") if isinstance(raw, dict) else None
        return sorted(
            f"ollama/{m['name'].removesuffix(':latest')}" for m in models or [] if m.get("name")
        )
