"""Serialisation for caches that leave the process (Redis)."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import TypeAdapter


class Codec[T](Protocol):
    def dumps(self, value: T) -> bytes: ...

    def loads(self, data: bytes) -> T: ...


class PydanticCodec[T]:
    """JSON codec for any type pydantic can validate, e.g. ``list[Aircraft]``."""

    def __init__(self, type_: Any) -> None:
        self._adapter: TypeAdapter[T] = TypeAdapter(type_)

    def dumps(self, value: T) -> bytes:
        return self._adapter.dump_json(value)

    def loads(self, data: bytes) -> T:
        return self._adapter.validate_json(data)
