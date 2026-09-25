"""Areas: the area registry, from the YAML.

Runs once Home Assistant has started, not during bootstrap: an area's
temperature and humidity sensors have to exist before the registry will
accept them, and they only exist once their integrations have loaded.

Everything that could make a write fail halfway — a floor or label that
doesn't exist, a sensor that isn't one, a name another area holds — is
checked while planning, so a bad YAML is reported before anything is written
instead of leaving half the areas updated.
"""

from __future__ import annotations

from typing import Any, Final

from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    floor_registry as fr,
    label_registry as lr,
)
from homeassistant.util import slugify

from ..model.areas import export_area, name_conflicts, normalize_name, render_area
from ..model.collection import CollectionPlan, Mode, plan_collection
from ..model.plan import Plan, Step
from .base import Kind, KindError, RunAt

KIND: Final = "areas"

_SENSOR_FIELDS: Final = {
    "temperature_entity_id": "temperature",
    "humidity_entity_id": "humidity",
}


def _fields(area: ar.AreaEntry) -> dict[str, Any]:
    """A live area in the same shape `render_area` produces."""
    return {
        "name": area.name,
        "icon": area.icon,
        "floor_id": area.floor_id,
        "aliases": sorted(area.aliases),
        "labels": sorted(area.labels),
        "picture": area.picture,
        "temperature_entity_id": area.temperature_entity_id,
        "humidity_entity_id": area.humidity_entity_id,
    }


def _registry_kwargs(fields: dict[str, Any]) -> dict[str, Any]:
    return {
        **fields,
        "aliases": set(fields["aliases"]),
        "labels": set(fields["labels"]),
    }


class AreasKind(Kind):
    name = KIND
    run_at = RunAt.STARTED

    async def async_plan(self) -> Plan:
        mode = Mode(self.conf["mode"])
        items = self.conf.get("items", {})
        if mode is Mode.EXCLUSIVE and not items:
            raise KindError(
                "mode: exclusive with no items would delete every area. List the "
                "areas, or use mode: owned to manage none of them."
            )
        desired = {key: render_area(item) for key, item in items.items()}
        self._check_references(desired)

        registry = ar.async_get(self.hass)
        live = {area.id: _fields(area) for area in registry.async_list_areas()}
        collection = plan_collection(
            desired, live, mode=mode, owned=self.ledger.owned(KIND)
        )
        deleting = {item.key for item in collection.deletes}
        conflicts = name_conflicts(desired, live, deleting)
        # `_create` briefly names an area after its key when the key isn't the
        # slug of its name, so that temporary name has to be free as well.
        held = {
            normalize_name(fields["name"]): key
            for key, fields in live.items()
            if key not in deleting
        }
        conflicts.extend(
            f"{item.key}: creating it needs the temporary name {item.key!r}, which "
            f"area {held[normalize_name(item.key)]!r} has"
            for item in collection.creates
            if slugify(desired[item.key]["name"]) != item.key
            and normalize_name(item.key) in held
        )
        if conflicts:
            raise KindError("Area names already in use: " + "; ".join(conflicts) + ".")

        steps = (
            *(Step(f"Delete area {item.key}") for item in collection.deletes),
            *(
                Step(f"Update area {item.key}", item.changes)
                for item in collection.updates
            ),
            *(
                Step(f"Create area {item.key}", item.changes)
                for item in collection.creates
            ),
        )
        return Plan(steps=steps, payload=(collection, desired))

    def _check_references(self, desired: dict[str, dict[str, Any]]) -> None:
        floors = fr.async_get(self.hass)
        labels = lr.async_get(self.hass)
        problems: list[str] = []
        for key, fields in sorted(desired.items()):
            if (
                fields["floor_id"]
                and floors.async_get_floor(fields["floor_id"]) is None
            ):
                problems.append(f"{key}: floor {fields['floor_id']!r} doesn't exist")
            problems.extend(
                f"{key}: label {label!r} doesn't exist"
                for label in fields["labels"]
                if labels.async_get_label(label) is None
            )
            for field, device_class in _SENSOR_FIELDS.items():
                entity_id = fields[field]
                if entity_id is None:
                    continue
                # The registry's own check (area_registry._validate_*_entity).
                state = self.hass.states.get(entity_id)
                if (
                    state is None
                    or state.domain != "sensor"
                    or state.attributes.get("device_class") != device_class
                ):
                    problems.append(
                        f"{key}: {entity_id} is not a {device_class} sensor"
                    )
        if problems:
            raise KindError("; ".join(problems) + ".")

    async def async_apply(self, plan: Plan) -> None:
        collection, desired = plan.payload
        registry = ar.async_get(self.hass)
        # Deletes first, so a name they free is available to the rest.
        for item in collection.deletes:
            registry.async_delete(item.key)
        for item in collection.updates:
            registry.async_update(item.key, **_registry_kwargs(desired[item.key]))
        for item in collection.creates:
            self._create(registry, item.key, desired[item.key])

    def _create(
        self, registry: ar.AreaRegistry, key: str, fields: dict[str, Any]
    ) -> None:
        """Create an area whose id is `key`.

        The registry takes no id: it derives one from the name, as its slug.
        When the name's slug is the key, that is all it takes. Otherwise the
        area is created under the key itself as its name — a slug that isn't
        taken, or this wouldn't be a create — and renamed straight after:
        ids never change on rename.
        """
        name = fields["name"]
        area = registry.async_create(name if slugify(name) == key else key)
        if area.id != key:
            registry.async_delete(area.id)
            raise KindError(
                f"Home Assistant gave the new area the id {area.id!r} instead of {key!r}."
            )
        registry.async_update(key, **_registry_kwargs(fields))

    async def async_verify(self, plan: Plan) -> None:
        collection, desired = plan.payload
        live = {
            area.id: _fields(area)
            for area in ar.async_get(self.hass).async_list_areas()
        }
        wrong = [key for key, fields in desired.items() if live.get(key) != fields]
        lingering = [item.key for item in collection.deletes if item.key in live]
        if wrong or lingering:
            raise KindError(
                "After the writes, areas don't match the YAML: "
                + ", ".join(sorted(wrong + lingering))
                + "."
            )

    async def async_remember(self, plan: Plan) -> None:
        # Also reached when already in sync: an area that matched on the first
        # run is owned from then on all the same.
        collection: CollectionPlan = plan.payload[0]
        await self.ledger.async_set_owned(KIND, collection.owned_after)

    @classmethod
    async def async_export(cls, hass: HomeAssistant) -> Any:
        registry = ar.async_get(hass)
        return {
            "mode": Mode.EXCLUSIVE.value,
            "items": {
                area.id: export_area(_fields(area))
                for area in registry.async_list_areas()
            },
        }
