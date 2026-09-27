"""FastAPI dependencies. Routers reach services only through these."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from argus.adapters.notify.webpush import VapidKeys
from argus.container import Container
from argus.infra.health import HealthRegistry
from argus.providers.registry import ProviderRegistry
from argus.services.alerts import AlertsService
from argus.services.analysis import AnalysisService
from argus.services.assistant.agent import AssistantService
from argus.services.assistant.notes import NotesService
from argus.services.assistant.prediction import PredictionAnalyst
from argus.services.assistant.search import SearchService
from argus.services.assistant.settings import AssistantSettingsService
from argus.services.aviation import AviationService
from argus.services.cyber import CyberService
from argus.services.events import EventsService
from argus.services.finance import FinanceService
from argus.services.imagery import ImageryService
from argus.services.infrastructure import InfrastructureService
from argus.services.maritime import MaritimeService
from argus.services.news import NewsService
from argus.services.preferences import PreferencesService
from argus.services.space import SpaceService
from argus.services.telegram import TelegramService
from argus.services.watchlists import WatchlistService

LOCAL_OWNER = "local"


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


def get_owner() -> str:
    """
    Whose data a request reads and writes.

    Argus is single-user for now, so every request acts as ``local``. This is
    the one seam to replace when authentication arrives: services and
    repositories already scope everything by owner.
    """
    return LOCAL_OWNER


def get_aviation_service(container: ContainerDep) -> AviationService:
    return container.aviation


def get_events_service(container: ContainerDep) -> EventsService:
    return container.events


def get_space_service(container: ContainerDep) -> SpaceService:
    return container.space


def get_maritime_service(container: ContainerDep) -> MaritimeService:
    return container.maritime


def get_infrastructure_service(container: ContainerDep) -> InfrastructureService:
    return container.infrastructure


def get_imagery_service(container: ContainerDep) -> ImageryService:
    return container.imagery


def get_news_service(container: ContainerDep) -> NewsService:
    return container.news


def get_telegram_service(container: ContainerDep) -> TelegramService:
    return container.telegram


def get_cyber_service(container: ContainerDep) -> CyberService:
    return container.cyber


def get_analysis_service(container: ContainerDep) -> AnalysisService:
    return container.analysis


def get_finance_service(container: ContainerDep) -> FinanceService:
    return container.finance


def get_watchlist_service(container: ContainerDep) -> WatchlistService:
    return container.watchlists


def get_preferences_service(container: ContainerDep) -> PreferencesService:
    return container.preferences


def get_assistant(container: ContainerDep) -> AssistantService:
    return container.assistant


def get_assistant_settings(container: ContainerDep) -> AssistantSettingsService:
    return container.assistant_settings


def get_notes(container: ContainerDep) -> NotesService:
    return container.notes


def get_prediction_analyst(container: ContainerDep) -> PredictionAnalyst:
    return container.prediction


def get_search(container: ContainerDep) -> SearchService:
    return container.search


def get_alerts(container: ContainerDep) -> AlertsService:
    return container.alerts


def get_vapid(container: ContainerDep) -> VapidKeys:
    return container.vapid


def get_health(container: ContainerDep) -> HealthRegistry:
    return container.health


def get_registry(container: ContainerDep) -> ProviderRegistry:
    return container.registry


OwnerDep = Annotated[str, Depends(get_owner)]
AviationServiceDep = Annotated[AviationService, Depends(get_aviation_service)]
EventsServiceDep = Annotated[EventsService, Depends(get_events_service)]
SpaceServiceDep = Annotated[SpaceService, Depends(get_space_service)]
MaritimeServiceDep = Annotated[MaritimeService, Depends(get_maritime_service)]
InfrastructureServiceDep = Annotated[InfrastructureService, Depends(get_infrastructure_service)]
ImageryServiceDep = Annotated[ImageryService, Depends(get_imagery_service)]
NewsServiceDep = Annotated[NewsService, Depends(get_news_service)]
TelegramServiceDep = Annotated[TelegramService, Depends(get_telegram_service)]
CyberServiceDep = Annotated[CyberService, Depends(get_cyber_service)]
AnalysisServiceDep = Annotated[AnalysisService, Depends(get_analysis_service)]
FinanceServiceDep = Annotated[FinanceService, Depends(get_finance_service)]
WatchlistServiceDep = Annotated[WatchlistService, Depends(get_watchlist_service)]
PreferencesServiceDep = Annotated[PreferencesService, Depends(get_preferences_service)]
HealthDep = Annotated[HealthRegistry, Depends(get_health)]
RegistryDep = Annotated[ProviderRegistry, Depends(get_registry)]
AssistantDep = Annotated[AssistantService, Depends(get_assistant)]
AssistantSettingsDep = Annotated[AssistantSettingsService, Depends(get_assistant_settings)]
NotesDep = Annotated[NotesService, Depends(get_notes)]
SearchDep = Annotated[SearchService, Depends(get_search)]
PredictionAnalystDep = Annotated[PredictionAnalyst, Depends(get_prediction_analyst)]
AlertsDep = Annotated[AlertsService, Depends(get_alerts)]
VapidDep = Annotated[VapidKeys, Depends(get_vapid)]
