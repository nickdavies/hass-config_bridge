"""`areas`: the area registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...lib.object_type import ObjectType
from .model import SCHEMA

if TYPE_CHECKING:
    from ...lib.kind import Kind


def _load_kind() -> type[Kind]:
    from .kind import AreasKind  # noqa: PLC0415

    return AreasKind


OBJECT_TYPE = ObjectType(name="areas", schema=SCHEMA, load_kind=_load_kind)
