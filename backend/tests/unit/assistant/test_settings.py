from argus.domain.llm import LlmConfig, StoredLlmSettings
from argus.services.assistant.settings import (
    AssistantSettingsService,
    SettingsSource,
    SettingsUpdate,
)
from tests.fakes import StubHttp


class MemoryRepo:
    def __init__(self) -> None:
        self.rows: dict[str, StoredLlmSettings] = {}

    async def get(self, owner: str) -> StoredLlmSettings | None:
        return self.rows.get(owner)

    async def save(self, owner: str, settings: StoredLlmSettings) -> None:
        self.rows[owner] = settings


ENV = LlmConfig(model="ollama/mistral", api_base="http://localhost:11434")


async def test_the_environment_is_the_default_and_the_app_wins() -> None:
    repo = MemoryRepo()
    service = AssistantSettingsService(repo, ENV, ("anthropic/claude-haiku-4-5",))
    view = await service.view("local")
    assert (view.model, view.source, view.key_set) == (
        "ollama/mistral",
        SettingsSource.ENVIRONMENT,
        False,
    )
    assert view.fallbacks == ("anthropic/claude-haiku-4-5",)
    assert await service.config("local") == ENV

    saved = await service.save(
        "local",
        SettingsUpdate(
            model="anthropic/claude-sonnet-5", api_base=None, api_key="sk-ant-abcdef1234"
        ),
    )
    assert (saved.source, saved.key_set, saved.key_hint) == (SettingsSource.APP, True, "…1234")
    assert await service.config("local") == LlmConfig(
        model="anthropic/claude-sonnet-5", api_key="sk-ant-abcdef1234"
    )


async def test_the_key_is_kept_unless_replaced_or_cleared() -> None:
    repo = MemoryRepo()
    service = AssistantSettingsService(repo, None)
    await service.save(
        "local", SettingsUpdate(model="openai/gpt-x", api_base=None, api_key="sk-1234567890")
    )
    await service.save("local", SettingsUpdate(model="openai/gpt-y", api_base=None))  # key omitted
    assert repo.rows["local"].api_key == "sk-1234567890"
    view = await service.save(
        "local", SettingsUpdate(model="openai/gpt-y", api_base=None, api_key="")
    )
    assert view.key_set is False
    assert repo.rows["local"].api_key is None


async def test_no_model_means_no_assistant() -> None:
    service = AssistantSettingsService(MemoryRepo(), None)
    assert (await service.view("local")).source is SettingsSource.NONE
    assert await service.config("local") is None
    await service.save("local", SettingsUpdate(model="", api_base=None))
    assert await service.config("local") is None


async def test_invalid_models_are_refused() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        await AssistantSettingsService(MemoryRepo(), None).save(
            "local", SettingsUpdate(model="rm -rf /", api_base=None)
        )


async def test_local_ollama_models_are_listed() -> None:
    http = StubHttp({"models": [{"name": "mistral:latest"}, {"name": "qwen2.5:7b"}]})
    service = AssistantSettingsService(MemoryRepo(), None, http=http)
    assert await service.local_models("http://localhost:11434/") == [
        "ollama/mistral",
        "ollama/qwen2.5:7b",
    ]
    assert http.calls[0][0] == "http://localhost:11434/api/tags"
    from argus.providers.errors import ProviderUnavailableError

    down = AssistantSettingsService(
        MemoryRepo(), None, http=StubHttp(error=ProviderUnavailableError("ollama", "x"))
    )
    assert await down.local_models("http://localhost:11434") == []
