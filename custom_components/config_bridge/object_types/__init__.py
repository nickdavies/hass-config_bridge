"""The object types the bridge manages, one package each.

Every package has the same shape:

- `model.py`: its YAML `SCHEMA` and every decision about what to write, with
  no Home Assistant imports, so it is unit tested on its own;
- `kind.py`: its `Kind`, which reads Home Assistant into plain data for the
  model and writes the model's plan back;
- `__init__.py`: its `OBJECT_TYPE`, which registers the two under its name.

The runner imports a Kind when it gets to it, inside that object type's
error boundary, so a Kind that fails to import stops that object type only.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from ..lib.object_type import ObjectType
from . import areas, entity_areas, http, mqtt, network

OBJECT_TYPES: Final[Mapping[str, ObjectType]] = {
    object_type.name: object_type
    for object_type in (
        http.OBJECT_TYPE,
        mqtt.OBJECT_TYPE,
        network.OBJECT_TYPE,
        # After areas: object types that run once Home Assistant has started
        # run in this order, and an entity can only go in an area that exists.
        areas.OBJECT_TYPE,
        entity_areas.OBJECT_TYPE,
    )
}
