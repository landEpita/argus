"""
Provider error hierarchy.

Only :class:`ProviderError` subclasses trigger a fallback to the next provider.
Anything else (``KeyError`` in a transform, a ``TypeError``) is a bug on our
side and must surface instead of being masked by a fallback.
"""

from __future__ import annotations


class ProviderError(Exception):
    """Base class for failures attributable to an upstream provider."""

    def __init__(self, provider: str, message: str) -> None:
        super().__init__(f"[{provider}] {message}")
        self.provider = provider


class ProviderUnavailableError(ProviderError):
    """Timeout, connection error, 429 or 5xx: the provider cannot answer now."""


class ProviderRateLimitedError(ProviderUnavailableError):
    """HTTP 429. ``retry_after_s`` is the provider's own estimate, when it gave one."""

    def __init__(self, provider: str, message: str, retry_after_s: float | None = None) -> None:
        super().__init__(provider, message)
        self.retry_after_s = retry_after_s


class ProviderResponseError(ProviderError):
    """The provider answered, but with something we cannot use."""


class ProviderNotFoundError(ProviderResponseError):
    """The provider has nothing for this key (HTTP 404): an answer, not a fault."""


class UnsupportedQueryError(ProviderError):
    """
    This provider cannot answer this particular query (e.g. adsb.lol only
    serves a 250 NM radius, so it cannot answer a whole-world request).
    Not a fault: the next provider is tried and health is left untouched.
    """


class NoProviderError(Exception):
    """No fetcher is registered for a capability."""

    def __init__(self, capability: str) -> None:
        super().__init__(f"no provider registered for capability '{capability}'")
        self.capability = capability


class AllProvidersFailedError(Exception):
    """Every registered fetcher for a capability failed."""

    def __init__(self, capability: str, errors: list[ProviderError]) -> None:
        detail = "; ".join(str(e) for e in errors)
        super().__init__(f"all providers failed for '{capability}': {detail}")
        self.capability = capability
        self.errors = errors

    @property
    def not_found(self) -> bool:
        """True when every provider that could answer said the thing does not exist."""
        relevant = [e for e in self.errors if not isinstance(e, UnsupportedQueryError)]
        return bool(relevant) and all(isinstance(e, ProviderNotFoundError) for e in relevant)

    @property
    def unsupported(self) -> bool:
        """True when no provider *failed*: none of them could serve this query."""
        return all(isinstance(e, UnsupportedQueryError) for e in self.errors)
