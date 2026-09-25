"""Areas, rendered from YAML and compared field by field.

The YAML key is the area id. Home Assistant derives an area's id from the
name it is created with and never changes it after, so the id is what
automations, templates and dashboards hold on to; the name is only a label
and can be edited freely. Keying on the id means a rename in the YAML is an
update, not a delete-and-recreate that would drop every device's assignment.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

FIELDS: Final = (
    "name",
    "icon",
    "floor_id",
    "aliases",
    "labels",
    "picture",
    "temperature_entity_id",
    "humidity_entity_id",
)
"""Everything an area has that a person sets. All of it is managed: a field
the YAML leaves out is cleared, the same as for every other kind."""


def render_area(conf: Mapping[str, Any]) -> dict[str, Any]:
    """An area as the YAML describes it, in the comparable shape.

    Aliases and labels are sets in Home Assistant; they are sorted lists here
    so a comparison and a report come out the same every time.
    """
    return {
        "name": conf["name"],
        "icon": conf.get("icon"),
        "floor_id": conf.get("floor_id"),
        "aliases": sorted(set(conf.get("aliases", ()))),
        "labels": sorted(set(conf.get("labels", ()))),
        "picture": conf.get("picture"),
        "temperature_entity_id": conf.get("temperature_entity_id"),
        "humidity_entity_id": conf.get("humidity_entity_id"),
    }


def normalize_name(name: str) -> str:
    """Home Assistant's rule for when two area names collide.

    Mirrors `homeassistant.helpers.normalized_name_base_registry
    .normalize_name`: case-folded, spaces removed. "Living Room" and
    "livingroom" are the same name as far as the registry is concerned.
    """
    return name.casefold().replace(" ", "")


def duplicate_names(items: Mapping[str, Mapping[str, Any]]) -> list[tuple[str, str]]:
    """Pairs of YAML keys whose names Home Assistant would treat as one."""
    seen: dict[str, str] = {}
    duplicates: list[tuple[str, str]] = []
    for key in sorted(items):
        normalized = normalize_name(items[key]["name"])
        if normalized in seen:
            duplicates.append((seen[normalized], key))
        else:
            seen[normalized] = key
    return duplicates


def name_conflicts(
    desired: Mapping[str, Mapping[str, Any]],
    live: Mapping[str, Mapping[str, Any]],
    deleting: set[str],
) -> list[str]:
    """Desired names already held by a different area that will still exist.

    The registry refuses a name another area has, and the bridge writes one
    area at a time, so this is checked before anything is written rather
    than discovered halfway through. It is deliberately stricter than the
    end state: two areas swapping names would conflict in the middle.
    """
    held = {
        normalize_name(fields["name"]): key
        for key, fields in live.items()
        if key not in deleting
    }
    conflicts = []
    for key in sorted(desired):
        holder = held.get(normalize_name(desired[key]["name"]))
        if holder is not None and holder != key:
            conflicts.append(
                f"{key}: the name {desired[key]['name']!r} belongs to area {holder!r}"
            )
    return conflicts


def export_area(fields: Mapping[str, Any]) -> dict[str, Any]:
    """An area as bridge YAML, with empty fields left out."""
    return {
        key: value for key, value in fields.items() if value is not None and value != []
    }
