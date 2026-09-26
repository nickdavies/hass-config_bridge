"""`devices`: the device registry, from the YAML and integrations' claims."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...lib.object_type import ObjectType
from .model import SCHEMA

if TYPE_CHECKING:
    from ...lib.kind import Kind


def _load_kind() -> type[Kind]:
    from .kind import DevicesKind  # noqa: PLC0415

    return DevicesKind


OBJECT_TYPE = ObjectType(
    name="devices", schema=SCHEMA, load_kind=_load_kind, runs_unlisted=True
)
