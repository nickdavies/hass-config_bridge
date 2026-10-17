"""Energy: the YAML's schema, and the energy preferences it renders to.

The preferences are one document: the energy sources (grid connections,
solar, batteries, gas and water meters) and the individual devices, in the
order the dashboard shows them. The YAML is the whole document, in the shape
Home Assistant stores it, so the keys are the ones `export` returns.

Each source is rendered with every key its type always stores, set to None
when the YAML leaves it out, as the energy configuration dialogs save it.
That way a dashboard set up in the UI and the same dashboard in YAML compare
equal.

Written against `.storage/energy` version 1.3. The Kind refuses to write to
any other version.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any, Final

import probatio

from ...lib.validators import entity_id, string

# --- the YAML ----------------------------------------------------------------

STATISTIC_ID_RE: Final = re.compile(
    r"^(?!.+__)(?!_)[\da-z_]+(?<!_)[.:](?!_)[\da-z_]+(?<!_)$"
)
"""An entity id, or an external statistic's `source:id`
(`homeassistant.components.recorder.statistics.VALID_STATISTIC_ID`)."""


def statistic_id(value: Any) -> str:
    """What the dashboard reads a meter from: an entity, or an external statistic."""
    text = string(value).lower()
    if not STATISTIC_ID_RE.match(text):
        raise probatio.Invalid(
            f"{text!r} is neither an entity id nor an external statistic id"
        )
    return text


_price: Final = probatio.Coerce(float)


def _one_power_method(conf: dict[str, Any]) -> dict[str, Any]:
    methods = ("stat_rate" in conf) + ("stat_rate_inverted" in conf)
    methods += "stat_rate_from" in conf
    if methods != 1:
        raise probatio.Invalid(
            "use one of stat_rate, stat_rate_inverted, or stat_rate_from with "
            "stat_rate_to"
        )
    return conf


_POWER_CONFIG: Final = probatio.All(
    probatio.Schema(
        {
            probatio.Optional("stat_rate"): statistic_id,
            probatio.Optional("stat_rate_inverted"): statistic_id,
            probatio.Inclusive("stat_rate_from", "two_sensors"): statistic_id,
            probatio.Inclusive("stat_rate_to", "two_sensors"): statistic_id,
        }
    ),
    _one_power_method,
)


def _not_both(*keys: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def validate(conf: dict[str, Any]) -> dict[str, Any]:
        if all(key in conf for key in keys):
            raise probatio.Invalid(f"give {' or '.join(keys)}, not both")
        return conf

    return validate


# Each type's keys, with their validators. `type` itself is checked by
# `_source`, which picks the type.
_GRID_FIELDS: Final = {
    "stat_energy_from": statistic_id,
    "stat_energy_to": statistic_id,
    "stat_cost": statistic_id,
    "entity_energy_price": entity_id,
    "number_energy_price": _price,
    "stat_compensation": statistic_id,
    "entity_energy_price_export": entity_id,
    "number_energy_price_export": _price,
    "stat_rate": statistic_id,
    "power_config": _POWER_CONFIG,
    "cost_adjustment_day": _price,
    "name": string,
}
_SOLAR_FIELDS: Final = {
    "stat_energy_from": statistic_id,
    "stat_rate": statistic_id,
    "config_entry_solar_forecast": [string],
    "name": string,
}
_BATTERY_FIELDS: Final = {
    "stat_energy_from": statistic_id,
    "stat_energy_to": statistic_id,
    "stat_rate": statistic_id,
    "power_config": _POWER_CONFIG,
    "stat_soc": statistic_id,
    "capacity": probatio.All(
        probatio.Coerce(float), probatio.Range(min=0, min_included=False)
    ),
    "name": string,
}
_METERED_FIELDS: Final = {
    "stat_energy_from": statistic_id,
    "stat_rate": statistic_id,
    "stat_cost": statistic_id,
    "entity_energy_price": entity_id,
    "number_energy_price": _price,
    "name": string,
}
"""Gas and water: a meter with an optional cost."""

SOURCE_FIELDS: Final[Mapping[str, Mapping[str, Any]]] = {
    "grid": _GRID_FIELDS,
    "solar": _SOLAR_FIELDS,
    "battery": _BATTERY_FIELDS,
    "gas": _METERED_FIELDS,
    "water": _METERED_FIELDS,
}

_REQUIRED: Final[Mapping[str, tuple[str, ...]]] = {
    "grid": (),
    "solar": ("stat_energy_from",),
    "battery": ("stat_energy_from", "stat_energy_to"),
    "gas": ("stat_energy_from",),
    "water": ("stat_energy_from",),
}


def _grid_measures_something(conf: dict[str, Any]) -> dict[str, Any]:
    if not conf.keys() & {
        "stat_energy_from",
        "stat_energy_to",
        "stat_rate",
        "power_config",
    }:
        raise probatio.Invalid(
            "a grid needs stat_energy_from, stat_energy_to, stat_rate or power_config"
        )
    return conf


_CHECKS: Final[Mapping[str, tuple[Callable[[dict[str, Any]], Any], ...]]] = {
    "grid": (
        _grid_measures_something,
        _not_both("entity_energy_price", "number_energy_price"),
        _not_both("entity_energy_price_export", "number_energy_price_export"),
        # Home Assistant would overwrite stat_rate with what power_config says.
        _not_both("stat_rate", "power_config"),
    ),
    "solar": (),
    "battery": (_not_both("stat_rate", "power_config"),),
    "gas": (_not_both("entity_energy_price", "number_energy_price"),),
    "water": (_not_both("entity_energy_price", "number_energy_price"),),
}


def _source_schema(source_type: str) -> Any:
    return probatio.All(
        probatio.Schema(
            {
                probatio.Required("type"): source_type,
                **{
                    (
                        probatio.Required(key)
                        if key in _REQUIRED[source_type]
                        else probatio.Optional(key)
                    ): validator
                    for key, validator in SOURCE_FIELDS[source_type].items()
                },
            }
        ),
        *_CHECKS[source_type],
    )


_SOURCE_SCHEMAS: Final = {
    source_type: _source_schema(source_type) for source_type in SOURCE_FIELDS
}


def _source(value: Any) -> dict[str, Any]:
    """One source, checked against its type's schema."""
    if not isinstance(value, Mapping):
        raise probatio.Invalid("expected a mapping with a type")
    source_type = value.get("type")
    if source_type not in _SOURCE_SCHEMAS:
        raise probatio.Invalid(
            f"type is one of {', '.join(_SOURCE_SCHEMAS)}", path=["type"]
        )
    return _SOURCE_SCHEMAS[source_type](value)


_DEVICE_FIELDS: Final = {
    "stat_consumption": statistic_id,
    "stat_rate": statistic_id,
    "name": string,
    "included_in_stat": statistic_id,
}

_DEVICE: Final = probatio.Schema(
    {
        (
            probatio.Required(key)
            if key == "stat_consumption"
            else probatio.Optional(key)
        ): validator
        for key, validator in _DEVICE_FIELDS.items()
    }
)

SCHEMA: Final = probatio.Schema(
    {
        probatio.Optional("energy_sources", default=list): [_source],
        probatio.Optional("device_consumption", default=list): [_DEVICE],
        probatio.Optional("device_consumption_water", default=list): [_DEVICE],
    }
)

# --- the preferences ---------------------------------------------------------

STORE_VERSION: Final = (1, 3)

LISTS: Final = ("energy_sources", "device_consumption", "device_consumption_water")
"""The preferences' keys, all of them lists. The whole of each is replaced."""

ALWAYS_STORED: Final[Mapping[str, tuple[str, ...]]] = {
    "grid": (
        "stat_energy_from",
        "stat_energy_to",
        "stat_cost",
        "entity_energy_price",
        "number_energy_price",
        "stat_compensation",
        "entity_energy_price_export",
        "number_energy_price_export",
    ),
    "solar": ("config_entry_solar_forecast",),
    "battery": (),
    "gas": ("stat_cost", "entity_energy_price", "number_energy_price"),
    "water": ("stat_cost", "entity_energy_price", "number_energy_price"),
}
"""Per source type, the keys stored as None when not set."""

PowerSensorId = Callable[[str, Mapping[str, str]], str]
"""Home Assistant's name for the sensor it makes from an inverted or
two-sensor `power_config`: `energy.helpers.generate_power_sensor_entity_id`."""


def render_energy(
    conf: Mapping[str, Any], power_sensor_id: PowerSensorId
) -> dict[str, list[dict[str, Any]]]:
    """The preferences the YAML describes, as Home Assistant stores them."""
    return {
        "energy_sources": [
            _render_source(source, power_sensor_id) for source in conf["energy_sources"]
        ],
        "device_consumption": [dict(device) for device in conf["device_consumption"]],
        "device_consumption_water": [
            dict(device) for device in conf["device_consumption_water"]
        ],
    }


def _render_source(
    source: Mapping[str, Any], power_sensor_id: PowerSensorId
) -> dict[str, Any]:
    source_type = source["type"]
    rendered: dict[str, Any] = {key: None for key in ALWAYS_STORED[source_type]}
    rendered.update(source)
    if source_type == "grid":
        rendered.setdefault("cost_adjustment_day", 0.0)
    # Home Assistant sets stat_rate from power_config as it saves: the sensor
    # itself, or the one it makes to invert or combine two.
    if power_config := source.get("power_config"):
        rendered["stat_rate"] = power_config.get("stat_rate") or power_sensor_id(
            source_type, power_config
        )
    return rendered


def unknown_keys(prefs: Mapping[str, Any]) -> list[str]:
    """Keys in the live preferences this rendering doesn't know about.

    The bridge replaces each list whole, so an unknown key in one of their
    items would be deleted.
    """
    unknown: list[str] = []
    for index, source in enumerate(prefs.get("energy_sources", [])):
        fields = SOURCE_FIELDS.get(source.get("type"))
        if fields is None:
            unknown.append(f"energy_sources[{index}].type: {source.get('type')}")
            continue
        unknown.extend(
            f"energy_sources[{index}].{key}"
            for key in source
            if key != "type" and key not in fields
        )
    for devices in LISTS[1:]:
        for index, device in enumerate(prefs.get(devices, [])):
            unknown.extend(
                f"{devices}[{index}].{key}"
                for key in device
                if key not in _DEVICE_FIELDS
            )
    return sorted(unknown)


def flatten(prefs: Mapping[str, Any]) -> dict[str, Any]:
    """The preferences as one field per item's key, for diffs a person can read.

    `energy_sources[0].number_energy_price` rather than the whole list.
    A list that changes length shows its extra or missing items' keys.
    """
    return {
        f"{name}[{index}].{key}": value
        for name in LISTS
        for index, item in enumerate(prefs.get(name, []))
        for key, value in item.items()
    }


def export_energy(prefs: Mapping[str, Any]) -> dict[str, Any]:
    """Live preferences as bridge YAML: unset keys and derived ones left out."""
    exported: dict[str, Any] = {}
    sources = [_export_source(source) for source in prefs.get("energy_sources", [])]
    if sources:
        exported["energy_sources"] = sources
    for devices in LISTS[1:]:
        if prefs.get(devices):
            exported[devices] = [_without_unset(item) for item in prefs[devices]]
    return exported


def _export_source(source: Mapping[str, Any]) -> dict[str, Any]:
    exported = _without_unset(source)
    if exported.get("cost_adjustment_day") == 0:
        del exported["cost_adjustment_day"]
    if "power_config" in exported:
        exported.pop("stat_rate", None)
    return exported


def _without_unset(item: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if value is not None}
