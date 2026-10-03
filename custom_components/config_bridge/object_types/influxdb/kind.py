"""InfluxDB: the connection config entry, from the YAML.

InfluxDB allows a single config entry, so the domain is the identity: an
entry created in the UI, or imported from the old YAML connection keys, is
adopted and updated in place, and one is created only if there is none.
The whole entry is replaced: `data` and title.
Switching between the 1.x and 2.x API is an update like any other.

Unlike MQTT, InfluxDB registers no update listener, so a set-up entry is
reloaded here after it is updated.
"""

from __future__ import annotations

from copy import deepcopy
from types import MappingProxyType
from typing import Any, Final

from homeassistant.config_entries import (
    SOURCE_IMPORT,
    ConfigEntry,
    ConfigEntryState,
)
from homeassistant.core import HomeAssistant

from ...lib.diff import FieldChange, creation_fields, diff_fields
from ...lib.kind import Kind, KindError
from ...lib.plan import Plan, Step
from . import model

INFLUXDB_DOMAIN: Final = "influxdb"

_RELOAD_STATES: Final = frozenset(
    (
        ConfigEntryState.LOADED,
        ConfigEntryState.SETUP_IN_PROGRESS,
        ConfigEntryState.SETUP_RETRY,
        ConfigEntryState.SETUP_ERROR,
    )
)
"""States in which the entry has read, or is reading, its old data."""


async def _check_entry_version(hass: HomeAssistant) -> None:
    """Refuse to write unless InfluxDB's current entry version is the rendered one.

    The version is on the flow handler, whose module imports InfluxDB's client
    libraries, so their requirements are installed first, as loading
    InfluxDB would.
    """
    from homeassistant.requirements import (  # noqa: PLC0415
        async_get_integration_with_requirements,
    )

    integration = await async_get_integration_with_requirements(hass, INFLUXDB_DOMAIN)
    flow = await integration.async_get_platform("config_flow")
    handler = flow.InfluxDBConfigFlow
    current = (handler.VERSION, handler.MINOR_VERSION)
    if current != model.ENTRY_VERSION:
        raise KindError(
            f"InfluxDB config entries are at version {current[0]}.{current[1]}; "
            f"this bridge renders {model.ENTRY_VERSION[0]}."
            f"{model.ENTRY_VERSION[1]}."
        )


def _entries(hass: HomeAssistant) -> list[ConfigEntry]:
    return hass.config_entries.async_entries(INFLUXDB_DOMAIN, include_ignore=False)


class InfluxdbKind(Kind):
    async def async_plan(self) -> Plan:
        await _check_entry_version(self.hass)
        rendered = model.render_influxdb(self.settings)
        entries = _entries(self.hass)
        if len(entries) > 1:
            raise KindError(
                f"Found {len(entries)} InfluxDB config entries; InfluxDB allows one."
            )
        if not entries:
            return Plan(
                steps=(Step("Create the InfluxDB config entry", _creation(rendered)),),
                payload=(None, rendered),
            )

        entry = entries[0]
        if (entry.version, entry.minor_version) != model.ENTRY_VERSION:
            raise KindError(
                f"The InfluxDB entry is at version {entry.version}."
                f"{entry.minor_version}; the bridge renders "
                f"{model.ENTRY_VERSION[0]}.{model.ENTRY_VERSION[1]}."
            )
        if unknown := model.unknown_keys(entry.data, entry.options):
            raise KindError(
                "The InfluxDB entry has settings the bridge doesn't know, and "
                f"replacing the entry would delete them: {', '.join(unknown)}."
            )
        changes = _changes(entry, rendered)
        if not changes:
            return Plan()
        return Plan(
            steps=(Step("Update the InfluxDB config entry in place", changes),),
            payload=(entry.entry_id, rendered),
        )

    async def async_apply(self, plan: Plan) -> None:
        entry_id, rendered = plan.payload
        if entry_id is None:
            await self.hass.config_entries.async_add(
                ConfigEntry(
                    data=deepcopy(rendered.data),
                    discovery_keys=MappingProxyType({}),
                    domain=INFLUXDB_DOMAIN,
                    minor_version=model.ENTRY_VERSION[1],
                    options={},
                    source=SOURCE_IMPORT,
                    subentries_data=None,
                    title=rendered.title,
                    unique_id=None,
                    version=model.ENTRY_VERSION[0],
                )
            )
            return

        entry = self.hass.config_entries.async_get_known_entry(entry_id)
        # Copies, so the entry never shares a dict with the plan and verify
        # compares what Home Assistant holds rather than the plan to itself.
        self.hass.config_entries.async_update_entry(
            entry, title=rendered.title, data=deepcopy(rendered.data), options={}
        )
        # InfluxDB has no update listener: an entry that has read the old data
        # keeps using it until reloaded. One not set up yet reads the new data
        # when it is.
        if entry.state in _RELOAD_STATES:
            self.hass.config_entries.async_schedule_reload(entry_id)

    async def async_verify(self, plan: Plan) -> None:
        _entry_id, rendered = plan.payload
        entries = _entries(self.hass)
        if len(entries) != 1 or _changes(entries[0], rendered):
            raise KindError(
                "After the write, the InfluxDB entry doesn't match the YAML."
            )

    @classmethod
    async def async_export(cls, hass: HomeAssistant) -> Any:
        entries = _entries(hass)
        if not entries:
            return {}
        return model.export_influxdb(entries[0].data)


def _creation(rendered: model.RenderedEntry) -> tuple[FieldChange, ...]:
    return creation_fields(rendered.data, secret_fields=model.SECRET_KEYS)


def _changes(
    entry: ConfigEntry, rendered: model.RenderedEntry
) -> tuple[FieldChange, ...]:
    return diff_fields({"title": rendered.title}, {"title": entry.title}) + diff_fields(
        rendered.data, entry.data, secret_fields=model.SECRET_KEYS
    )
