"""Domain errors. The API maps each to one HTTP status in ``api/errors.py``."""

from __future__ import annotations


class DomainError(Exception):
    """Base class for rule violations the caller can fix."""


class NotFoundError(DomainError):
    def __init__(self, entity: str, key: object) -> None:
        super().__init__(f"{entity} '{key}' not found")
        self.entity = entity
        self.key = key


class ConflictError(DomainError):
    """The request clashes with existing state (e.g. a duplicate name)."""


class LimitExceededError(DomainError):
    """A per-owner quota would be exceeded."""
