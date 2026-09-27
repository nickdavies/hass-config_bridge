"""Entities: the YAML's schema, other integrations' claims, and the plan.

Each item pins one entity registry entry to what git says:

    entities:
      items:
        light.kitchen_lights_all:
          area_id: kitchen
        sensor.fridge_door_battery:
          hidden: true

Every field a person can set on an entity in the UI and the bridge manages is
pinned, whether the item sets it or not: a field left out is put back to the
integration's own value. That includes the entity id itself, so an entity
renamed in the UI is renamed back.

Other integrations add items for their own entities with `claim_entities`
(see `config_bridge.claims`), in the same shape. An entity may be listed
once, by the YAML or by one integration (`lib.claims`).

The bridge manages only the entities that are listed or claimed. One that
stops being listed is released: its fields are put back to the integration's
own values once, and it is left alone from then on.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

import probatio

from ...lib.claims import claimed_by
from ...lib.diff import FieldChange, diff_fields
from ...lib.validators import (
    ensure_list,
    icon,
    keyed_by_entity_id,
    slug,
    string,
)

# --- the YAML ----------------------------------------------------------------

ITEM_SCHEMA: Final = probatio.All(
    # `light.x:` with nothing under it pins every field to its default.
    lambda value: {} if value is None else value,
    probatio.Schema(
        {
            probatio.Optional("area_id"): slug,
            probatio.Optional("name"): string,
            probatio.Optional("icon"): icon,
            probatio.Optional("aliases"): probatio.All(ensure_list, [string]),
            probatio.Optional("labels"): probatio.All(ensure_list, [slug]),
            probatio.Optional("hidden"): probatio.Boolean(),
            probatio.Optional("disabled"): probatio.Boolean(),
        }
    ),
)

ITEMS_SCHEMA: Final = keyed_by_entity_id(ITEM_SCHEMA)

SCHEMA: Final = probatio.Schema(
    {probatio.Optional("items", default=dict): ITEMS_SCHEMA}
)

# --- rendering and comparing -------------------------------------------------


def render(item: Mapping[str, Any]) -> dict[str, Any]:
    """An entity as an item describes it, in the comparable shape.

    - `aliases` are the ones a person adds. The entity's own name is always
      an alias too, as it is for a new entity: `name_is_alias`.
    - `hidden` and `disabled` are whether a *user* hid or disabled it. An
      integration hiding or disabling its own entity is left alone.
    - `device_class` is the user's override; the integration's own always
      applies.
    """
    return {
        "area_id": item.get("area_id"),
        "name": item.get("name"),
        "icon": item.get("icon"),
        "device_class": None,
        "aliases": sorted(set(item.get("aliases", ()))),
        "name_is_alias": True,
        "labels": sorted(set(item.get("labels", ()))),
        "hidden": bool(item.get("hidden", False)),
        "disabled": bool(item.get("disabled", False)),
    }


DEFAULTS: Final = render({})
"""What a released entity is put back to: the integration's own values."""


def export_item(fields: Mapping[str, Any]) -> dict[str, Any] | None:
    """An entity as bridge YAML, with default fields left out; None if all are."""
    exported = {
        key: value
        for key, value in fields.items()
        if key not in ("device_class", "name_is_alias") and value != DEFAULTS[key]
    }
    return exported or None


# --- planning ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LiveEntity:
    """One entity registry entry, as the Kind read it."""

    registry_id: str
    """The registry's own id for the entry, which a rename doesn't change."""
    entity_id: str
    fields: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class EntityChange:
    """The writes one entry needs. `changes` lists only fields that move."""

    entity_id: str
    """Where the entity belongs: its listed id, or its current one if released."""
    current_entity_id: str
    registry_id: str
    owner: str | None
    """Who listed it; None when it is being released."""
    fields: Mapping[str, Any]
    """Every managed field as it should end up, not only the ones that move."""
    changes: tuple[FieldChange, ...]

    @property
    def summary(self) -> str:
        if self.owner is None:
            return f"Release {self.entity_id}, putting back its own values"
        return f"Pin {self.entity_id}{claimed_by(self.owner)}"


@dataclass(frozen=True, slots=True)
class EntitiesPlan:
    changes: tuple[EntityChange, ...]
    problems: tuple[str, ...]
    owned_after: dict[str, str]
    """Listed entity id to registry id, for the ledger."""


def plan_entities(
    desired: Mapping[str, tuple[str, Mapping[str, Any]]],
    live: Mapping[str, LiveEntity],
    owned: Mapping[str, str],
) -> EntitiesPlan:
    """What to write so every listed entity matches, and every released one
    is back to its own values.

    `live` is every registry entry by its current entity id. `owned` is what
    the ledger remembered: listed entity id to registry id. That is how an
    entity renamed in the UI is found again, under the id it was renamed to.
    """
    by_registry_id = {entry.registry_id: entry for entry in live.values()}

    def find(entity_id: str) -> LiveEntity | None:
        remembered = by_registry_id.get(owned.get(entity_id, ""))
        return remembered if remembered is not None else live.get(entity_id)

    changes: list[EntityChange] = []
    problems: list[str] = []
    owned_after: dict[str, str] = {}
    for entity_id in sorted(desired):
        owner, fields = desired[entity_id]
        entry = find(entity_id)
        if entry is None:
            problems.append(f"{entity_id}: no such entity in the entity registry")
            continue
        holder = live.get(entity_id)
        if holder is not None and holder.registry_id != entry.registry_id:
            problems.append(
                f"{entity_id}: renamed to {entry.entity_id} in the UI, and another "
                "entity has since taken its id"
            )
            continue
        owned_after[entity_id] = entry.registry_id
        moves = diff_fields(fields, entry.fields)
        if entry.entity_id != entity_id:
            moves = (FieldChange("entity_id", entry.entity_id, entity_id), *moves)
        if moves:
            changes.append(
                EntityChange(
                    entity_id, entry.entity_id, entry.registry_id, owner, fields, moves
                )
            )

    for entity_id in sorted(owned.keys() - desired.keys()):
        entry = find(entity_id)
        if entry is None:
            continue  # gone from the registry; nothing left to release
        if moves := diff_fields(DEFAULTS, entry.fields):
            changes.append(
                EntityChange(
                    entry.entity_id,
                    entry.entity_id,
                    entry.registry_id,
                    None,
                    DEFAULTS,
                    moves,
                )
            )

    return EntitiesPlan(tuple(changes), tuple(problems), owned_after)


def missing_references(
    desired: Mapping[str, tuple[str, Mapping[str, Any]]],
    areas: set[str],
    labels: set[str],
) -> list[str]:
    """Areas and labels the items name that Home Assistant doesn't have."""
    problems = []
    for entity_id in sorted(desired):
        owner, fields = desired[entity_id]
        by = claimed_by(owner)
        if fields["area_id"] is not None and fields["area_id"] not in areas:
            problems.append(
                f"{entity_id}{by}: area {fields['area_id']!r} doesn't exist"
            )
        problems.extend(
            f"{entity_id}{by}: label {label!r} doesn't exist"
            for label in fields["labels"]
            if label not in labels
        )
    return problems
