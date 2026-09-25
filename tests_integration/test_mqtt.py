"""MQTT against Home Assistant's real config entries.

MQTT itself is never set up here — that would try to reach a broker. The
entries are real; creating one has its setup patched out, and an existing one
is left unloaded, which is also what the bridge meets on a boot where it runs
before MQTT.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.config_bridge.model.mqtt import DEFAULT_BIRTH, DEFAULT_WILL

from .conftest import SetupBridge, report

BROKER = "mosquitto.automation.svc.cluster.local"
YAML = {"broker": BROKER, "username": "hass", "password": "hunter2"}

DATA = {
    "broker": BROKER,
    "port": 1883,
    "protocol": "5",
    "transport": "tcp",
    "username": "hass",
    "password": "hunter2",
}
OPTIONS = {
    "discovery": True,
    "discovery_prefix": "homeassistant",
    "discovery_qos": 0,
    "birth_message": DEFAULT_BIRTH,
    "will_message": DEFAULT_WILL,
}

# What an entry made in the UI years ago might look like.
UI_ENTRY = {
    "domain": "mqtt",
    "version": 2,
    "minor_version": 1,
    "title": "mqtt.internal.example.com",
    "data": {
        "broker": "mqtt.internal.example.com",
        "port": 1883,
        "protocol": "3.1.1",
        "transport": "tcp",
        "username": "hass",
        "password": "old",
    },
    "options": {"discovery": True, "discovery_prefix": "homeassistant"},
}


def only_entry(hass: HomeAssistant):
    [entry] = hass.config_entries.async_entries("mqtt")
    return entry


async def test_creates_the_entry_when_there_is_none(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_setup",
        AsyncMock(return_value=True),
    ):
        await setup_bridge({"mqtt": YAML})

    entry = only_entry(hass)
    assert entry.title == BROKER
    assert dict(entry.data) == DATA
    assert dict(entry.options) == OPTIONS
    assert (entry.version, entry.minor_version) == (2, 1)
    assert entry.source == SOURCE_IMPORT
    assert report(hass, "mqtt") is None


async def test_updates_a_ui_entry_in_place(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    existing = MockConfigEntry(**UI_ENTRY)
    existing.add_to_hass(hass)

    await setup_bridge({"mqtt": YAML})

    entry = only_entry(hass)
    assert entry.entry_id == existing.entry_id
    assert entry.title == BROKER
    assert dict(entry.data) == DATA
    assert dict(entry.options) == OPTIONS


async def test_in_sync_touches_nothing(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    existing = MockConfigEntry(
        domain="mqtt",
        version=2,
        minor_version=1,
        title=BROKER,
        data=DATA,
        options=OPTIONS,
    )
    existing.add_to_hass(hass)
    modified_at = existing.modified_at

    await setup_bridge({"mqtt": YAML})

    assert only_entry(hass).modified_at == modified_at
    assert report(hass, "mqtt") is None


async def test_reloads_an_entry_caught_mid_setup(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    existing = MockConfigEntry(**UI_ENTRY, state=ConfigEntryState.SETUP_IN_PROGRESS)
    existing.add_to_hass(hass)

    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        await setup_bridge({"mqtt": YAML})

    reload.assert_called_once_with(existing.entry_id)


async def test_unknown_settings_are_reported_not_deleted(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    ui = {**UI_ENTRY, "data": {**UI_ENTRY["data"], "tls_version": "1.2"}}
    MockConfigEntry(**ui).add_to_hass(hass)

    await setup_bridge({"mqtt": YAML})

    assert only_entry(hass).data["tls_version"] == "1.2"
    issue = report(hass, "mqtt")
    assert issue is not None
    assert "data.tls_version" in issue.translation_placeholders["reason"]


async def test_unmigrated_entry_waits(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    MockConfigEntry(**{**UI_ENTRY, "version": 1, "minor_version": 1}).add_to_hass(hass)

    await setup_bridge({"mqtt": YAML})

    assert only_entry(hass).data["broker"] == "mqtt.internal.example.com"
    assert "version 1.1" in report(hass, "mqtt").translation_placeholders["reason"]


async def test_two_entries_are_reported(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    MockConfigEntry(**UI_ENTRY).add_to_hass(hass)
    MockConfigEntry(**UI_ENTRY).add_to_hass(hass)

    await setup_bridge({"mqtt": YAML})

    assert "Found 2" in report(hass, "mqtt").translation_placeholders["reason"]


async def test_report_never_shows_the_password(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    MockConfigEntry(**UI_ENTRY).add_to_hass(hass)

    await setup_bridge({"mqtt": {**YAML, "report_only": True}})

    assert only_entry(hass).data["password"] == "old"
    changes = report(hass, "mqtt").translation_placeholders["changes"]
    assert "password: changed (<redacted>)" in changes
    assert "hunter2" not in changes
    assert "old" not in changes.replace("protocol: 3.1.1", "")
