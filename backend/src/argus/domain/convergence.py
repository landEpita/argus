"""
Converging signals: places where several *independent* kinds of signal
coincide — reported violence, military aircraft, air-raid alerts, disasters,
fire hotspots, military vessels.

Co-location is a reason to look, not a conclusion: an air base next to a city
in the news will converge every day. Signals placed at a country's centroid
(Internet outages) are excluded on purpose: they would fabricate co-location.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pydantic import Field

from argus.domain.base import DomainModel
from argus.domain.geo import BoundingBox, GeoPoint

CELL_DEG = 2.0
MIN_KINDS = 2


class SignalKind(StrEnum):
    REPORTED_VIOLENCE = "reported_violence"
    MILITARY_AIRCRAFT = "military_aircraft"
    AIR_ALERT = "air_alert"
    DISASTER = "disaster"
    FIRE = "fire"
    MILITARY_VESSEL = "military_vessel"


@dataclass(frozen=True, slots=True)
class SignalPoint:
    kind: SignalKind
    id: str
    label: str
    position: GeoPoint
    at: datetime
    country: str | None = None  # only when the source itself says so


class KindCount(DomainModel):
    kind: SignalKind
    count: int
    examples: tuple[str, ...] = Field(description="Up to three labels")


class Convergence(DomainModel):
    id: str = Field(description="Grid cell id, stable across refreshes")
    cell: BoundingBox
    center: GeoPoint = Field(description="Mean position of the signals, not the cell centre")
    kinds: tuple[KindCount, ...]
    score: float
    latest: datetime
    country: str | None = Field(
        default=None, description="Most cited by the signals themselves; None if none say"
    )


def _cell(point: GeoPoint) -> tuple[int, int]:
    return math.floor(point.lon / CELL_DEG), math.floor(point.lat / CELL_DEG)


def find(points: Iterable[SignalPoint], min_kinds: int = MIN_KINDS) -> list[Convergence]:
    """Cells with at least ``min_kinds`` distinct kinds, strongest first."""
    cells: dict[tuple[int, int], list[SignalPoint]] = defaultdict(list)
    for p in points:
        cells[_cell(p.position)].append(p)

    found: list[Convergence] = []
    for (x, y), members in cells.items():
        by_kind: dict[SignalKind, list[SignalPoint]] = defaultdict(list)
        for p in members:
            by_kind[p.kind].append(p)
        if len(by_kind) < min_kinds:
            continue
        # Diversity first: each extra kind outweighs any number of repeats of one kind.
        score = sum(1 + math.log1p(len(ps)) for ps in by_kind.values())
        west, south = x * CELL_DEG, y * CELL_DEG
        cited = Counter(p.country for p in members if p.country)
        found.append(
            Convergence(
                id=f"cell:{x}:{y}",
                cell=BoundingBox(
                    west=max(west, -180),
                    south=max(south, -90),
                    east=min(west + CELL_DEG, 180),
                    north=min(south + CELL_DEG, 90),
                ),
                center=GeoPoint(
                    lat=sum(p.position.lat for p in members) / len(members),
                    lon=sum(p.position.lon for p in members) / len(members),
                ),
                kinds=tuple(
                    KindCount(
                        kind=kind,
                        count=len(ps),
                        examples=tuple(dict.fromkeys(p.label for p in ps))[:3],
                    )
                    for kind, ps in sorted(by_kind.items(), key=lambda kv: -len(kv[1]))
                ),
                score=round(score, 2),
                latest=max(p.at for p in members),
                country=cited.most_common(1)[0][0] if cited else None,
            )
        )
    found.sort(key=lambda c: (len(c.kinds), c.score), reverse=True)
    return found
