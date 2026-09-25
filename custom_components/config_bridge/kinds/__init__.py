"""The adapters, one per kind. Adding a kind means adding it here and to
`model/schema.py`'s `KIND_SCHEMAS`."""

from __future__ import annotations

from typing import Final

from .areas import AreasKind
from .base import Kind
from .http import HttpKind
from .mqtt import MqttKind
from .network import NetworkKind

KINDS: Final[dict[str, type[Kind]]] = {
    kind.name: kind for kind in (HttpKind, MqttKind, NetworkKind, AreasKind)
}
