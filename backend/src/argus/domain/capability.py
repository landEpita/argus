"""
Capabilities are the ports of the hexagon.

A capability names *what* the platform needs ("current aircraft states in a
box") together with its query and result types, without saying *who* provides
it. Adapters register fetchers against a capability; services only ever ask
for the capability. Swapping OpenSky for adsb.lol is then a registration
change, never a service change.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Capability[Q, R]:
    """A typed token. ``Q`` is the query model, ``R`` the result type."""

    name: str
    description: str = ""

    def __str__(self) -> str:
        return self.name
