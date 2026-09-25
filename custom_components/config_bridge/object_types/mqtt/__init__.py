"""`mqtt`: the MQTT broker connection, MQTT's config entry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...lib.object_type import ObjectType
from .model import SCHEMA

if TYPE_CHECKING:
    from ...lib.kind import Kind


def _load_kind() -> type[Kind]:
    from .kind import MqttKind  # noqa: PLC0415

    return MqttKind


OBJECT_TYPE = ObjectType(name="mqtt", schema=SCHEMA, load_kind=_load_kind)
