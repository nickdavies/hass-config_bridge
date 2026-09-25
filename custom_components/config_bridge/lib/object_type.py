"""How an object type is registered with the bridge."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .kind import Kind


@dataclass(frozen=True, slots=True)
class ObjectType:
    """One kind of thing the bridge manages, as the engine sees it."""

    name: str
    """The key its YAML goes under, and the name its logs and repair issue use."""

    schema: Callable[[Any], Any]
    """Validates its YAML. Imports no Home Assistant: it is part of
    `CONFIG_SCHEMA`."""

    load_kind: Callable[[], type[Kind]]
    """Imports its `Kind`. The runner calls it inside the object type's error
    boundary, so a Kind that fails to import stops that object type only."""
