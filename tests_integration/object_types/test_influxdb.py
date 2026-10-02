"""InfluxDB against Home Assistant's real config entries.

InfluxDB itself is never set up here — that would try to reach a server.
The entries are real; creating one has its setup patched out, and an
existing one is left unloaded unless a test says otherwise. Checking the
entry version imports InfluxDB's config flow, so its client libraries have
to be installed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from ..conftest import SetupBridge, report

URL = "http://influxdb.observability.svc.cluster.local:8086"
YAML = {
    "url": URL,
    "token": "hunter2",
    "organization": "0123456789abcdef",
    "bucket": "homeassistant",
}
DATA = {"api_version": "2", **YAML, "verify_ssl": True}
TITLE = f"homeassistant ({URL})"

# An entry made in the UI, before the bridge managed it.
UI_ENTRY = {
    "domain": "influxdb",
    "version": 1,
    "minor_version": 1,
    "title": "old (https://influx.example.com)",
    "data": {
        "api_version": "2",
        "url": "https://influx.example.com",
        "token": "old",
        "organization": "0123456789abcdef",
        "bucket": "old",
        "verify_ssl": False,
    },
}


def only_entry(hass: HomeAssistant):
    [entry] = hass.config_entries.async_entries("influxdb")
    return entry


async def test_creates_the_entry_when_there_is_none(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_setup",
        AsyncMock(return_value=True),
    ):
        await setup_bridge({"influxdb": YAML})

    entry = only_entry(hass)
    assert entry.title == TITLE
    assert dict(entry.data) == DATA
    assert dict(entry.options) == {}
    assert (entry.version, entry.minor_version) == (1, 1)
    assert entry.source == SOURCE_IMPORT
    assert report(hass, "influxdb") is None


async def test_updates_a_ui_entry_in_place(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    existing = MockConfigEntry(**UI_ENTRY)
    existing.add_to_hass(hass)

    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        await setup_bridge({"influxdb": YAML})

    entry = only_entry(hass)
    assert entry.entry_id == existing.entry_id
    assert entry.title == TITLE
    assert dict(entry.data) == DATA
    # Not set up: it reads the new data when it is.
    reload.assert_not_called()


async def test_replaces_an_imported_v1_entry(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    v1 = {
        "api_version": "1",
        "host": "localhost",
        "port": None,
        "username": None,
        "password": None,
        "database": "home_assistant",
        "ssl": None,
        "path": None,
        "verify_ssl": True,
        "ssl_ca_cert": None,
    }
    MockConfigEntry(**{**UI_ENTRY, "data": v1}).add_to_hass(hass)

    await setup_bridge({"influxdb": YAML})

    assert dict(only_entry(hass).data) == DATA


async def test_reloads_a_loaded_entry(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    existing = MockConfigEntry(**UI_ENTRY, state=ConfigEntryState.LOADED)
    existing.add_to_hass(hass)

    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        await setup_bridge({"influxdb": YAML})

    reload.assert_called_once_with(existing.entry_id)


async def test_in_sync_touches_nothing(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    existing = MockConfigEntry(
        domain="influxdb",
        version=1,
        minor_version=1,
        title=TITLE,
        data=DATA,
        state=ConfigEntryState.LOADED,
    )
    existing.add_to_hass(hass)
    modified_at = existing.modified_at

    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        await setup_bridge({"influxdb": YAML})

    assert only_entry(hass).modified_at == modified_at
    reload.assert_not_called()
    assert report(hass, "influxdb") is None


async def test_unknown_settings_are_reported_not_deleted(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    ui = {**UI_ENTRY, "data": {**UI_ENTRY["data"], "timeout": 5}}
    MockConfigEntry(**ui).add_to_hass(hass)

    await setup_bridge({"influxdb": YAML})

    assert only_entry(hass).data["timeout"] == 5
    issue = report(hass, "influxdb")
    assert issue is not None
    assert "data.timeout" in issue.translation_placeholders["reason"]


async def test_an_entry_at_another_version_is_reported(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    MockConfigEntry(**{**UI_ENTRY, "version": 2}).add_to_hass(hass)

    await setup_bridge({"influxdb": YAML})

    assert only_entry(hass).data["bucket"] == "old"
    assert "version 2.1" in report(hass, "influxdb").translation_placeholders["reason"]


async def test_report_never_shows_the_token(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    MockConfigEntry(**UI_ENTRY).add_to_hass(hass)

    await setup_bridge({"influxdb": {**YAML, "report_only": True}})

    assert only_entry(hass).data["token"] == "old"
    changes = report(hass, "influxdb").translation_placeholders["changes"]
    assert "token: changed (<redacted>)" in changes
    assert "hunter2" not in changes
