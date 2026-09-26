"""Entity areas: the entity registry's area assignments, from the YAML.

Runs once Home Assistant has started, and after `areas` (object types that
run then go in registry order): an entity can only be put in an area that
exists, and the areas themselves may be created by `areas` on the same boot.

An entity the YAML lists has to be in the entity registry already. Entities
of an integration that is still loading, or that discovers its entities over
MQTT, are in the registry from the boot they were first seen on, so this only
bites on the very first boot after one appears; the report says which, and
the next boot applies it.

State kept in the ledger: `owned`, the entity ids the YAML listed when it
last matched. An entity is cleared only if it is owned and has left the
YAML. Losing it leaves those entities in their last area rather than clearing
them.
"""

from __future__ import annotations

from typing import Any, Final

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, entity_registry as er

from ...lib.collection import CollectionPlan, Mode, plan_collection
from ...lib.kind import Kind, KindError, RunAt
from ...lib.plan import Plan, Step
from .model import export, missing_references, render

OWNED: Final = "owned"
"""Ledger key: the entity ids whose area the bridge manages."""


class EntityAreasKind(Kind):
    run_at = RunAt.STARTED

    async def async_plan(self) -> Plan:
        desired = render(self.settings.get("items", {}))
        entities = er.async_get(self.hass)
        areas = {area.id for area in ar.async_get(self.hass).async_list_areas()}
        if problems := missing_references(desired, entities.entities.keys(), areas):
            raise KindError("; ".join(problems) + ".")

        owned = frozenset(self.state.get(OWNED, ()))
        live = {
            entity: {"area_id": entry.area_id}
            for entity in desired.keys() | owned
            if (entry := entities.async_get(entity)) is not None
        }
        collection = plan_collection(desired, live, mode=Mode.OWNED, owned=owned)
        # An entity that left the YAML with no area already needs nothing
        # done; it simply stops being owned.
        clears = tuple(
            item.key for item in collection.deletes if live[item.key]["area_id"]
        )
        steps = (
            *(
                Step(
                    f"Take {key} out of area {live[key]['area_id']!r}",
                )
                for key in clears
            ),
            *(
                Step(f"Put {item.key} in its area", item.changes)
                for item in collection.updates
            ),
        )
        return Plan(steps=steps, payload=(collection, desired, clears))

    async def async_apply(self, plan: Plan) -> None:
        collection, desired, clears = plan.payload
        entities = er.async_get(self.hass)
        for key in clears:
            entities.async_update_entity(key, area_id=None)
        for item in collection.updates:
            entities.async_update_entity(item.key, area_id=desired[item.key]["area_id"])

    async def async_verify(self, plan: Plan) -> None:
        _collection, desired, clears = plan.payload
        entities = er.async_get(self.hass)

        def area_of(key: str) -> str | None:
            entry = entities.async_get(key)
            return entry.area_id if entry is not None else None

        wrong = sorted(
            [
                key
                for key, fields in desired.items()
                if area_of(key) != fields["area_id"]
            ]
            + [key for key in clears if area_of(key) is not None]
        )
        if wrong:
            raise KindError(
                "After the writes, these entities' areas don't match the YAML: "
                + ", ".join(wrong)
                + "."
            )

    async def async_remember(self, plan: Plan) -> None:
        collection: CollectionPlan = plan.payload[0]
        await self.state.async_set(OWNED, sorted(collection.owned_after))

    @classmethod
    async def async_export(cls, hass: HomeAssistant) -> Any:
        return export(
            {
                entry.entity_id: entry.area_id
                for entry in er.async_get(hass).entities.values()
            }
        )
