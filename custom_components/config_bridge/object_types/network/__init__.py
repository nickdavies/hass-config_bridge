"""`network`: the adapters discovery listens on, in `.storage/core.network`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...lib.object_type import ObjectType
from .model import SCHEMA

if TYPE_CHECKING:
    from ...lib.kind import Kind


def _load_kind() -> type[Kind]:
    from .kind import NetworkKind  # noqa: PLC0415

    return NetworkKind


OBJECT_TYPE = ObjectType(name="network", schema=SCHEMA, load_kind=_load_kind)
