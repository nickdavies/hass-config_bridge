"""`http`: the HTTP server's settings, in Home Assistant's `.storage/http`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...lib.object_type import ObjectType
from .model import SCHEMA

if TYPE_CHECKING:
    from ...lib.kind import Kind


def _load_kind() -> type[Kind]:
    from .kind import HttpKind  # noqa: PLC0415

    return HttpKind


OBJECT_TYPE = ObjectType(name="http", schema=SCHEMA, load_kind=_load_kind)
