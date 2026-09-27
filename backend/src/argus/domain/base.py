"""Common base for domain models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """
    Immutable value object.

    ``json_schema_serialization_defaults_required`` makes response schemas
    list defaulted fields as required: the API always sends them, and the
    generated TypeScript types should say so instead of marking them optional.
    """

    model_config = ConfigDict(frozen=True, json_schema_serialization_defaults_required=True)
