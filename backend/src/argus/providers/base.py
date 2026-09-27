"""
The Fetcher contract (Template Method).

Every upstream integration follows the same three steps, borrowed from the
OpenBB platform's provider model:

1. ``transform_query`` — domain query -> provider request parameters (pure)
2. ``extract``         — perform the I/O and return the raw payload
3. ``transform``       — raw payload -> normalised domain objects (pure)

Keeping steps 1 and 3 pure means almost all of an adapter is testable from a
recorded fixture, without the network.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel


class Fetcher[Q: BaseModel, R](ABC):
    # A class attribute for most adapters; an instance may override it when one
    # class serves several upstreams (e.g. two Overpass mirrors).
    provider_name: str

    async def fetch(self, query: Q) -> R:
        params = self.transform_query(query)
        raw = await self.extract(params)
        return self.transform(query, raw)

    def transform_query(self, query: Q) -> Mapping[str, str]:
        return {}

    @abstractmethod
    async def extract(self, params: Mapping[str, str]) -> Any:
        """Fetch the raw payload. Raise a ProviderError subclass on failure."""

    @abstractmethod
    def transform(self, query: Q, raw: Any) -> R:
        """Normalise the raw payload. Raise ProviderResponseError if unusable."""
