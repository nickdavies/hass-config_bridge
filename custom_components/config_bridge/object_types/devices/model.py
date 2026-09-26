"""Devices: the YAML's schema, and the plan.

Each item pins one device registry entry to what git says. Devices are keyed
by an identifier their integration gives them, under the integration's
domain, since that is what stays the same across rebuilds (a device's
registry id doesn't, and its name is one of the things pinned):

    devices:
      items:
        mqtt:
          zigbee2mqtt_0x001788010c6f92e4:
            area_id: dining
            name: Dining centre 1

The integration's own name, model and so on are its business. What a person
can set in the UI is pinned, whether the item sets it or not: its area, the
name it is shown by, its labels, and whether a user disabled it. A field left
out goes back to its default.

Other integrations add items for their own devices with `claim_devices`, in
the same shape, and the bridge manages only the devices that are listed or
claimed. One that stops being listed is released: its fields go back to
their defaults once, and it is left alone from then on. A device's default
area is none.
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
    keyed_by_slug,
    slug,
    string,
)

# --- the YAML ----------------------------------------------------------------

ITEM_SCHEMA: Final = probatio.All(
    # A device with nothing under it pins every field to its default.
    lambda value: {} if value is None else value,
    probatio.Schema(
        {
            probatio.Optional("area_id"): slug,
            probatio.Optional("name"): string,
            probatio.Optional("labels"): probatio.All(ensure_list, [slug]),
            probatio.Optional("disabled"): probatio.Boolean(),
        }
    ),
)


def _by_identifier(value: Any) -> dict[str, Any]:
    """One integration's devices: identifier to item."""
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise probatio.Invalid("expected a mapping of device identifier to settings")
    validated: dict[str, Any] = {}
    for key, item in value.items():
        identifier = string(key)
        try:
            validated[identifier] = ITEM_SCHEMA(item)
        except probatio.Invalid as err:
            raise probatio.Invalid(err.msg, path=[key, *err.path]) from err
    return validated


ITEMS_SCHEMA: Final = keyed_by_slug(_by_identifier)
"""Integration domain, to identifier, to item."""

SCHEMA: Final = probatio.Schema(
    {probatio.Optional("items", default=dict): ITEMS_SCHEMA}
)

# --- keys ----------------------------------------------------------------------

type DeviceKey = tuple[str, str]
"""A device identifier: the integration's domain and its own id for it."""


def flatten(items: Mapping[str, Mapping[str, Any]]) -> dict[DeviceKey, Any]:
    """The YAML's nesting, as one mapping keyed by identifier."""
    return {
        (domain, identifier): item
        for domain, devices in items.items()
        for identifier, item in devices.items()
    }


def describe(key: DeviceKey) -> str:
    """A device identifier as a report shows it."""
    return f"{key[0]} {key[1]}"


# --- rendering and comparing -------------------------------------------------


def render(item: Mapping[str, Any]) -> dict[str, Any]:
    """A device as an item describes it, in the comparable shape.

    `name` is the name a person gives it (`name_by_user`), not the
    integration's own. `disabled` is whether a *user* disabled it.
    """
    return {
        "area_id": item.get("area_id"),
        "name": item.get("name"),
        "labels": sorted(set(item.get("labels", ()))),
        "disabled": bool(item.get("disabled", False)),
    }


DEFAULTS: Final = render({})


def export_item(fields: Mapping[str, Any]) -> dict[str, Any] | None:
    """A device as bridge YAML, with default fields left out; None if all are."""
    exported = {key: value for key, value in fields.items() if value != DEFAULTS[key]}
    return exported or None


# --- planning ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LiveDevice:
    """One device registry entry, as the Kind read it."""

    registry_id: str
    fields: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class DeviceChange:
    """The writes one device needs. `changes` lists only fields that move."""

    key: DeviceKey
    registry_id: str
    owner: str | None
    """Who listed it; None when it is being released."""
    fields: Mapping[str, Any]
    changes: tuple[FieldChange, ...]

    @property
    def summary(self) -> str:
        if self.owner is None:
            return f"Release device {describe(self.key)}, putting back its defaults"
        return f"Pin device {describe(self.key)}{claimed_by(self.owner)}"


@dataclass(frozen=True, slots=True)
class DevicesPlan:
    changes: tuple[DeviceChange, ...]
    problems: tuple[str, ...]
    owned_after: tuple[DeviceKey, ...]


def plan_devices(
    desired: Mapping[DeviceKey, tuple[str, Mapping[str, Any]]],
    live: Mapping[DeviceKey, LiveDevice],
    owned: set[DeviceKey],
) -> DevicesPlan:
    """What to write so every listed device matches, and every released one is
    back to its defaults. `live` has the devices the listed and owned
    identifiers find."""
    changes: list[DeviceChange] = []
    problems: list[str] = []
    for key in sorted(desired):
        owner, fields = desired[key]
        device = live.get(key)
        if device is None:
            problems.append(
                f"device {describe(key)}{claimed_by(owner)}: no such device in the "
                "device registry"
            )
            continue
        if moves := diff_fields(fields, device.fields):
            changes.append(DeviceChange(key, device.registry_id, owner, fields, moves))
    for key in sorted(owned - desired.keys()):
        device = live.get(key)
        if device is not None and (moves := diff_fields(DEFAULTS, device.fields)):
            changes.append(DeviceChange(key, device.registry_id, None, DEFAULTS, moves))
    owned_after = tuple(key for key in sorted(desired) if key in live)
    return DevicesPlan(tuple(changes), tuple(problems), owned_after)


def missing_references(
    desired: Mapping[DeviceKey, tuple[str, Mapping[str, Any]]],
    areas: set[str],
    labels: set[str],
) -> list[str]:
    """Areas and labels the items name that Home Assistant doesn't have."""
    problems = []
    for key in sorted(desired):
        owner, fields = desired[key]
        where = f"device {describe(key)}{claimed_by(owner)}"
        if fields["area_id"] is not None and fields["area_id"] not in areas:
            problems.append(f"{where}: area {fields['area_id']!r} doesn't exist")
        problems.extend(
            f"{where}: label {label!r} doesn't exist"
            for label in fields["labels"]
            if label not in labels
        )
    return problems
