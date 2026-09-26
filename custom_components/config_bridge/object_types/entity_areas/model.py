"""Entity areas: the YAML's schema, and the checks made before anything is written.

Each item assigns one entity to one area:

    entity_areas:
      items:
        light.kitchen_lights_all: kitchen

This is the entity's own area, which takes precedence over its device's. The
bridge manages only the entities it lists: an entity it assigned is cleared
once it leaves the YAML, and entities it never listed are left as they are,
so assignments made in the UI or inherited from a device are untouched.
"""

from __future__ import annotations

from collections.abc import Mapping, Set
from typing import Any, Final

import probatio

from ...lib.validators import keyed_by_entity_id, slug

# --- the YAML ----------------------------------------------------------------

SCHEMA: Final = probatio.Schema(
    {
        probatio.Optional("items", default=dict): keyed_by_entity_id(slug),
    }
)

# --- rendering and checking --------------------------------------------------


def render(items: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    """The YAML's items in the shape `plan_collection` compares."""
    return {entity: {"area_id": area} for entity, area in items.items()}


def missing_references(
    desired: Mapping[str, Mapping[str, Any]],
    entities: Set[str],
    areas: Set[str],
) -> list[str]:
    """Entities and areas the YAML names that Home Assistant doesn't have.

    Checked before anything is written, so a typo or an entity that hasn't
    been discovered yet is reported instead of half the assignments made.
    """
    problems = []
    for entity in sorted(desired):
        if entity not in entities:
            problems.append(f"{entity}: no such entity in the entity registry")
        area = desired[entity]["area_id"]
        if area not in areas:
            problems.append(f"{entity}: area {area!r} doesn't exist")
    return problems


def export(assignments: Mapping[str, str | None]) -> dict[str, Any]:
    """Every entity that has an area of its own, as bridge YAML."""
    return {
        "items": {
            entity: area
            for entity, area in sorted(assignments.items())
            if area is not None
        }
    }
