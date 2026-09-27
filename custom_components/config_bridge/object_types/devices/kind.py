"""Devices: device registry entries pinned to the YAML and to integrations' claims.

Runs once Home Assistant has started, after `areas` and before `entities`:
every integration has set up by then, so their devices are registered and
their claims made, and an area the YAML creates on this boot already exists.

Everything that would make a write fail (a device that isn't registered, an
area or label that doesn't exist, a device listed twice) is checked while
planning, so nothing is written until all of it is right. Only the fields
that differ are written: a device its integration or config entry disabled
stays that way unless an item says otherwise.

State kept in the ledger: `owned`, the identifiers listed when they last
matched, for releasing. Losing it means a device no longer listed keeps its
pinned values rather than being released.
"""

from __future__ import annotations

from typing import Any, Final

from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    label_registry as lr,
)

from ...lib.claims import claims_for, merge_claims
from ...lib.diff import FieldChange
from ...lib.kind import Kind, KindError, RunAt
from ...lib.plan import Plan, Step
from .model import (
    DeviceKey,
    DevicesPlan,
    LiveDevice,
    describe,
    export_item,
    flatten,
    missing_references,
    plan_devices,
    render,
)

OWNED: Final = "owned"
"""Ledger key: the listed device identifiers, as [domain, identifier] pairs."""


def _fields(device: dr.DeviceEntry) -> dict[str, Any]:
    """A live device in the same shape `render` produces."""
    return {
        "area_id": device.area_id,
        "name": device.name_by_user,
        "labels": sorted(device.labels),
        "disabled": device.disabled_by is dr.DeviceEntryDisabler.USER,
    }


def _kwargs(changes: tuple[FieldChange, ...]) -> dict[str, Any]:
    """`async_update_device` arguments for the fields that move."""
    kwargs: dict[str, Any] = {}
    for change in changes:
        if change.field == "name":
            kwargs["name_by_user"] = change.new
        elif change.field == "labels":
            kwargs["labels"] = set(change.new)
        elif change.field == "disabled":
            kwargs["disabled_by"] = dr.DeviceEntryDisabler.USER if change.new else None
        else:
            kwargs[change.field] = change.new
    return kwargs


class DevicesKind(Kind):
    run_at = RunAt.STARTED

    async def async_plan(self) -> Plan:
        claims = {
            owner: flatten(items)
            for owner, items in claims_for(self.hass.data, "devices").items()
        }
        desired, conflicts = merge_claims(
            flatten(self.settings.get("items", {})), claims, render, describe
        )
        owned: set[DeviceKey] = {
            (domain, identifier) for domain, identifier in self.state.get(OWNED, [])
        }
        registry = dr.async_get(self.hass)
        live: dict[DeviceKey, LiveDevice] = {}
        ambiguous: list[str] = []
        for key in sorted(desired.keys() | owned):
            # Identifiers are unique only within a config entry, so two
            # integrations' devices can share one. Pinning either would be a
            # guess.
            match registry.async_get_devices(identifiers={key}):
                case [device]:
                    live[key] = LiveDevice(device.id, _fields(device))
                case []:
                    pass
                case found:
                    ambiguous.append(
                        f"device {describe(key)}: {len(found)} devices have this "
                        "identifier"
                    )
        devices = plan_devices(desired, live, owned)
        areas = {area.id for area in ar.async_get(self.hass).async_list_areas()}
        labels = {
            label.label_id for label in lr.async_get(self.hass).async_list_labels()
        }
        problems = [
            *conflicts,
            *ambiguous,
            *missing_references(desired, areas, labels),
            *devices.problems,
        ]
        if problems:
            raise KindError("; ".join(problems) + ".")
        steps = tuple(
            Step(change.summary, change.changes) for change in devices.changes
        )
        return Plan(steps=steps, payload=devices)

    async def async_apply(self, plan: Plan) -> None:
        devices: DevicesPlan = plan.payload
        registry = dr.async_get(self.hass)
        for change in devices.changes:
            registry.async_update_device(change.registry_id, **_kwargs(change.changes))

    async def async_verify(self, plan: Plan) -> None:
        devices: DevicesPlan = plan.payload
        registry = dr.async_get(self.hass)
        wrong = [
            describe(change.key)
            for change in devices.changes
            if (device := registry.async_get(change.registry_id)) is None
            or _fields(device) != change.fields
        ]
        if wrong:
            raise KindError(
                "After the writes, these devices don't match what was listed: "
                + ", ".join(sorted(wrong))
                + "."
            )

    async def async_remember(self, plan: Plan) -> None:
        devices: DevicesPlan = plan.payload
        await self.state.async_set(
            OWNED, [list(key) for key in devices.owned_after] or None
        )

    @classmethod
    async def async_export(cls, hass: HomeAssistant) -> Any:
        items: dict[str, dict[str, Any]] = {}
        for device in dr.async_get(hass).devices.values():
            if not device.identifiers:
                continue
            item = export_item(_fields(device))
            if item is None:
                continue
            domain, identifier = min(device.identifiers)
            items.setdefault(domain, {})[identifier] = item
        return {
            "items": {
                domain: dict(sorted(d.items())) for domain, d in sorted(items.items())
            }
        }
