"""MQTT: the broker connection config entry, from the YAML.

MQTT allows a single config entry, so the domain is the identity: an entry
created in the UI is adopted and updated in place — same entry id, so its
devices, entities and history stay attached — and one is created only if
there is none. The whole entry is replaced: `data`, `options` and title.
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

MQTT_DOMAIN: Final = "mqtt"


def _check_entry_version() -> None:
    """Refuse to write unless MQTT's current entry version is the rendered one."""
    from homeassistant.components.mqtt import const as mqtt_const  # noqa: PLC0415

    current = (mqtt_const.CONFIG_ENTRY_VERSION, mqtt_const.CONFIG_ENTRY_MINOR_VERSION)
    if current != model.ENTRY_VERSION:
        raise KindError(
            f"MQTT config entries are at version {current[0]}.{current[1]}; this "
            f"bridge renders {model.ENTRY_VERSION[0]}.{model.ENTRY_VERSION[1]}."
        )


def _entries(hass: HomeAssistant) -> list[ConfigEntry]:
    return hass.config_entries.async_entries(MQTT_DOMAIN, include_ignore=False)


class MqttKind(Kind):
    async def async_plan(self) -> Plan:
        _check_entry_version()
        rendered = model.render_mqtt(self.settings)
        entries = _entries(self.hass)
        if len(entries) > 1:
            raise KindError(
                f"Found {len(entries)} MQTT config entries; MQTT allows one."
            )
        if not entries:
            return Plan(
                steps=(Step("Create the MQTT config entry", _creation(rendered)),),
                payload=(None, rendered),
            )

        entry = entries[0]
        if (entry.version, entry.minor_version) != model.ENTRY_VERSION:
            raise KindError(
                f"The MQTT entry is at version {entry.version}."
                f"{entry.minor_version}; Home Assistant migrates it when MQTT "
                "loads, and the bridge updates it on a boot after that."
            )
        if unknown := model.unknown_keys(entry.data, entry.options):
            raise KindError(
                "The MQTT entry has settings the bridge doesn't know, and "
                f"replacing the entry would delete them: {', '.join(unknown)}."
            )
        changes = _changes(entry, rendered)
        if not changes:
            return Plan()
        return Plan(
            steps=(Step("Update the MQTT config entry in place", changes),),
            payload=(entry.entry_id, rendered),
        )

    async def async_apply(self, plan: Plan) -> None:
        entry_id, rendered = plan.payload
        if entry_id is None:
            await self.hass.config_entries.async_add(
                ConfigEntry(
                    data=deepcopy(rendered.data),
                    discovery_keys=MappingProxyType({}),
                    domain=MQTT_DOMAIN,
                    minor_version=model.ENTRY_VERSION[1],
                    options=deepcopy(rendered.options),
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
            entry,
            title=rendered.title,
            data=deepcopy(rendered.data),
            options=deepcopy(rendered.options),
        )
        # A loaded MQTT entry reloads itself on update — it registers an update
        # listener. One that is still setting up may have read the old data
        # before registering it, so it is reloaded once setup finishes. One not
        # set up yet reads the new data when it is.
        if entry.state is ConfigEntryState.SETUP_IN_PROGRESS:
            self.hass.config_entries.async_schedule_reload(entry_id)

    async def async_verify(self, plan: Plan) -> None:
        _entry_id, rendered = plan.payload
        entries = _entries(self.hass)
        if len(entries) != 1 or _changes(entries[0], rendered):
            raise KindError("After the write, the MQTT entry doesn't match the YAML.")

    @classmethod
    async def async_export(cls, hass: HomeAssistant) -> Any:
        entries = _entries(hass)
        if not entries:
            return {}
        return model.export_mqtt(entries[0].data, entries[0].options)


def _creation(rendered: model.RenderedEntry) -> tuple[FieldChange, ...]:
    return creation_fields(
        {**rendered.data, **rendered.options}, secret_fields=model.SECRET_KEYS
    )


def _changes(
    entry: ConfigEntry, rendered: model.RenderedEntry
) -> tuple[FieldChange, ...]:
    return (
        diff_fields({"title": rendered.title}, {"title": entry.title})
        + diff_fields(rendered.data, entry.data, secret_fields=model.SECRET_KEYS)
        + diff_fields(rendered.options, entry.options, secret_fields=model.SECRET_KEYS)
    )
