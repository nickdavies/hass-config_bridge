"""`energy`: the energy dashboard's preferences, in `.storage/energy`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...lib.object_type import ObjectType
from .model import SCHEMA

if TYPE_CHECKING:
    from ...lib.kind import Kind


def _load_kind() -> type[Kind]:
    from .kind import EnergyKind  # noqa: PLC0415

    return EnergyKind


OBJECT_TYPE = ObjectType(name="energy", schema=SCHEMA, load_kind=_load_kind)
