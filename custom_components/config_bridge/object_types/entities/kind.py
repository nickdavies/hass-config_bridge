"""Entities: entity registry entries pinned to the YAML and to integrations' claims.

Runs once Home Assistant has started, after `areas`: every integration has
set up by then, so their entities are registered and their claims made, and
an area the YAML creates on this boot already exists.

Everything that would make a write fail (an entity that isn't registered, an
area or label that doesn't exist, an entity listed twice) is checked while
planning, so nothing is written until all of it is right.

Only the fields that differ are written. That matters for `hidden` and
`disabled`: an entity its integration hid or disabled stays that way unless
an item says otherwise.

State kept in the ledger: `owned`, each listed entity id and its entry's
registry id, from when they last matched. The registry id is what finds an
entity renamed in the UI, and the list is what says which entities to
release. Losing it means an entity renamed in the UI since is reported
missing rather than renamed back, and one no longer listed keeps its pinned
values rather than being released.
"""

from __future__ import annotations

from typing import Any, Final

from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    entity_registry as er,
    label_registry as lr,
)

from ...lib.claims import claims_for, merge_claims
from ...lib.diff import FieldChange
from ...lib.kind import Kind, KindError, RunAt
from ...lib.plan import Plan, Step
from .model import (
    EntitiesPlan,
    LiveEntity,
    export_item,
    missing_references,
    plan_entities,
    render,
)

OWNED: Final = "owned"
"""Ledger key: listed entity id to registry id."""


def _fields(entry: er.RegistryEntry) -> dict[str, Any]:
    """A live entry in the same shape `render` produces."""
    if not isinstance(entry.aliases, list):
        raise KindError(
            "Entity aliases aren't a list with the computed name in it, as in the "
            "Home Assistant release this was written against."
        )
    return {
        "area_id": entry.area_id,
        "name": entry.name,
        "icon": entry.icon,
        "device_class": entry.device_class,
        "aliases": sorted(alias for alias in entry.aliases if isinstance(alias, str)),
        "name_is_alias": er.COMPUTED_NAME in entry.aliases,
        "labels": sorted(entry.labels),
        "hidden": entry.hidden_by is er.RegistryEntryHider.USER,
        "disabled": entry.disabled_by is er.RegistryEntryDisabler.USER,
    }


def _live(registry: er.EntityRegistry) -> dict[str, LiveEntity]:
    return {
        entry.entity_id: LiveEntity(entry.id, entry.entity_id, _fields(entry))
        for entry in registry.entities.values()
    }


def _kwargs(changes: tuple[FieldChange, ...], wanted: dict[str, Any]) -> dict[str, Any]:
    """`async_update_entity` arguments for the fields that move.

    Aliases are written whole whenever either alias field moves, since they
    are one list in the registry.
    """
    kwargs: dict[str, Any] = {}
    for change in changes:
        field = change.field
        if field == "entity_id":
            kwargs["new_entity_id"] = change.new
        elif field in ("aliases", "name_is_alias"):
            computed = [er.COMPUTED_NAME] if wanted["name_is_alias"] else []
            kwargs["aliases"] = [*computed, *wanted["aliases"]]
        elif field == "labels":
            kwargs["labels"] = set(change.new)
        elif field == "hidden":
            kwargs["hidden_by"] = er.RegistryEntryHider.USER if change.new else None
        elif field == "disabled":
            kwargs["disabled_by"] = (
                er.RegistryEntryDisabler.USER if change.new else None
            )
        else:
            kwargs[field] = change.new
    return kwargs


class EntitiesKind(Kind):
    run_at = RunAt.STARTED

    async def async_plan(self) -> Plan:
        desired, conflicts = merge_claims(
            self.settings.get("items", {}),
            claims_for(self.hass.data, "entities"),
            render,
        )
        areas = {area.id for area in ar.async_get(self.hass).async_list_areas()}
        labels = {
            label.label_id for label in lr.async_get(self.hass).async_list_labels()
        }
        entities = plan_entities(
            desired, _live(er.async_get(self.hass)), self.state.get(OWNED, {})
        )
        problems = [
            *conflicts,
            *missing_references(desired, areas, labels),
            *entities.problems,
        ]
        if problems:
            raise KindError("; ".join(problems) + ".")
        steps = tuple(
            Step(change.summary, change.changes) for change in entities.changes
        )
        return Plan(steps=steps, payload=entities)

    async def async_apply(self, plan: Plan) -> None:
        entities: EntitiesPlan = plan.payload
        registry = er.async_get(self.hass)
        for change in entities.changes:
            registry.async_update_entity(
                change.current_entity_id, **_kwargs(change.changes, change.fields)
            )

    async def async_verify(self, plan: Plan) -> None:
        entities: EntitiesPlan = plan.payload
        registry = er.async_get(self.hass)
        wrong = [
            change.entity_id
            for change in entities.changes
            if (entry := registry.async_get(change.entity_id)) is None
            or entry.id != change.registry_id
            or _fields(entry) != change.fields
        ]
        if wrong:
            raise KindError(
                "After the writes, these entities don't match what was listed: "
                + ", ".join(sorted(wrong))
                + "."
            )

    async def async_remember(self, plan: Plan) -> None:
        entities: EntitiesPlan = plan.payload
        await self.state.async_set(OWNED, entities.owned_after or None)

    @classmethod
    async def async_export(cls, hass: HomeAssistant) -> Any:
        items = {}
        for entry in sorted(
            er.async_get(hass).entities.values(), key=lambda e: e.entity_id
        ):
            if (item := export_item(_fields(entry))) is not None:
                items[entry.entity_id] = item
        return {"items": items}
