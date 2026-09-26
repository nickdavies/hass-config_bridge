"""`entity_areas`: the area each listed entity is in."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...lib.object_type import ObjectType
from .model import SCHEMA

if TYPE_CHECKING:
    from ...lib.kind import Kind


def _load_kind() -> type[Kind]:
    from .kind import EntityAreasKind  # noqa: PLC0415

    return EntityAreasKind


OBJECT_TYPE = ObjectType(name="entity_areas", schema=SCHEMA, load_kind=_load_kind)
