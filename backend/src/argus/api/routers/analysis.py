from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel

from argus.api.deps import AnalysisServiceDep
from argus.domain.convergence import Convergence
from argus.domain.news import Story
from argus.domain.signal_index import RULES, Component, CountrySignal, HistoryPoint

router = APIRouter(prefix="/analysis", tags=["analysis"])


class InputStatusOut(BaseModel):
    name: str
    ok: bool
    error: str | None


class ComponentRuleOut(BaseModel):
    component: Component
    max_points: float
    rule: str


class CountrySignalCollection(BaseModel):
    count: int
    items: list[CountrySignal]
    inputs: list[InputStatusOut]
    method: list[ComponentRuleOut]


class CountryDetailOut(BaseModel):
    iso2: str
    name: str
    signal: CountrySignal | None
    history: list[HistoryPoint]
    stories: list[Story]
    inputs: list[InputStatusOut]


class ConvergenceCollection(BaseModel):
    count: int
    items: list[Convergence]
    inputs: list[InputStatusOut]


METHOD = [
    ComponentRuleOut(component=c, max_points=r.max_points, rule=r.description)
    for c, r in RULES.items()
]


@router.get("/countries", response_model=CountrySignalCollection)
async def country_signals(service: AnalysisServiceDep) -> CountrySignalCollection:
    """Country Signal Index: disruptive activity the feeds report now (not stability)."""
    result = await service.country_signals()
    return CountrySignalCollection(
        count=len(result.items),
        items=result.items,
        inputs=[InputStatusOut(name=i.name, ok=i.ok, error=i.error) for i in result.inputs],
        method=METHOD,
    )


@router.get("/countries/{iso2}", response_model=CountryDetailOut)
async def country_detail(
    service: AnalysisServiceDep, iso2: Annotated[str, Path(pattern=r"^[A-Za-z]{2}$")]
) -> CountryDetailOut:
    detail = await service.country(iso2)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"unknown country '{iso2}'")
    return CountryDetailOut(
        iso2=detail.iso2,
        name=detail.name,
        signal=detail.signal,
        history=detail.history,
        stories=detail.stories,
        inputs=[InputStatusOut(name=i.name, ok=i.ok, error=i.error) for i in detail.inputs],
    )


@router.get("/convergence", response_model=ConvergenceCollection)
async def convergence(service: AnalysisServiceDep) -> ConvergenceCollection:
    """Places where several independent kinds of signal coincide. A lead, not a finding."""
    result = await service.convergence()
    return ConvergenceCollection(
        count=len(result.items),
        items=result.items,
        inputs=[InputStatusOut(name=i.name, ok=i.ok, error=i.error) for i in result.inputs],
    )
