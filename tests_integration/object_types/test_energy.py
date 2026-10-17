"""Energy against Home Assistant's real energy manager and its websocket API.

The energy integration needs the recorder, so every test that sets it up
takes `recorder_mock`. Preferences "saved in the UI" go through the same
websocket command the energy dialogs send, so a test that finds them in sync
shows the bridge renders what the UI stores.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.components.energy.data import async_get_manager
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from ..conftest import SetupBridge, report

GRID = {
    "type": "grid",
    "stat_energy_from": "sensor.xcel_grid_current_summation_delivered_value",
    "stat_energy_to": "sensor.xcel_grid_current_summation_received_value",
}
SOLAR = {
    "type": "solar",
    "stat_energy_from": "sensor.xcel_solar_current_summation_delivered_value",
}

# What the energy dialogs send for those two: every field, unset ones null
# (`emptyGridSourceEnergyPreference` and `emptySolarEnergyPreference` in the
# frontend's src/data/energy.ts).
GRID_FROM_UI = {
    **GRID,
    "stat_cost": None,
    "stat_compensation": None,
    "entity_energy_price": None,
    "number_energy_price": None,
    "entity_energy_price_export": None,
    "number_energy_price_export": None,
    "cost_adjustment_day": 0,
}
SOLAR_FROM_UI = {**SOLAR, "config_entry_solar_forecast": None}


@pytest.fixture
async def energy(recorder_mock: Any, hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "energy", {})


async def save_in_ui(hass: HomeAssistant, hass_ws_client: Any, **prefs: Any) -> None:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "energy/save_prefs", **prefs})
    assert (await client.receive_json())["success"]


@pytest.mark.usefixtures("energy")
async def test_creates_the_preferences(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    await setup_bridge({"energy": {"energy_sources": [GRID, SOLAR]}})

    manager = await async_get_manager(hass)
    assert manager.data == {
        "energy_sources": [
            {**GRID_FROM_UI, "cost_adjustment_day": 0.0},
            SOLAR_FROM_UI,
        ],
        "device_consumption": [],
        "device_consumption_water": [],
    }
    assert report(hass, "energy") is None


@pytest.mark.usefixtures("energy")
async def test_the_same_dashboard_saved_in_the_ui_is_in_sync(
    hass: HomeAssistant, setup_bridge: SetupBridge, hass_ws_client: Any
) -> None:
    await save_in_ui(
        hass,
        hass_ws_client,
        energy_sources=[GRID_FROM_UI, SOLAR_FROM_UI],
        device_consumption=[],
        device_consumption_water=[],
    )
    manager = await async_get_manager(hass)

    with patch.object(manager, "async_update") as update:
        await setup_bridge({"energy": {"energy_sources": [GRID, SOLAR]}})

    update.assert_not_called()
    assert report(hass, "energy") is None


@pytest.mark.usefixtures("energy")
async def test_puts_back_what_the_ui_changed(
    hass: HomeAssistant, setup_bridge: SetupBridge, hass_ws_client: Any
) -> None:
    await save_in_ui(
        hass,
        hass_ws_client,
        energy_sources=[{**GRID_FROM_UI, "number_energy_price": 0.15}],
        device_consumption=[{"stat_consumption": "sensor.fridge_energy"}],
    )

    await setup_bridge({"energy": {"energy_sources": [GRID, SOLAR]}})

    manager = await async_get_manager(hass)
    assert manager.data["energy_sources"][0]["number_energy_price"] is None
    assert manager.data["energy_sources"][1] == SOLAR_FROM_UI
    assert manager.data["device_consumption"] == []
    assert report(hass, "energy") is None


@pytest.mark.usefixtures("energy")
async def test_power_config_gets_home_assistants_stat_rate(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    grid = {**GRID, "power_config": {"stat_rate_inverted": "sensor.grid_power"}}

    await setup_bridge({"energy": {"energy_sources": [grid]}})

    manager = await async_get_manager(hass)
    assert manager.data["energy_sources"][0]["stat_rate"] == (
        "sensor.grid_power_inverted"
    )
    assert report(hass, "energy") is None


@pytest.mark.usefixtures("energy")
async def test_home_assistants_own_rules_report(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    # Two grid connections can't share an import meter. Only Home Assistant's
    # schema knows that.
    await setup_bridge({"energy": {"energy_sources": [GRID, GRID]}})

    manager = await async_get_manager(hass)
    assert manager.data is None
    reason = report(hass, "energy").translation_placeholders["reason"]
    assert "used in multiple grid connections" in reason


@pytest.mark.usefixtures("energy")
async def test_unknown_keys_report(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    manager = await async_get_manager(hass)
    manager.data = {
        "energy_sources": [{**SOLAR_FROM_UI, "forecast_tilt": 30}],
        "device_consumption": [],
        "device_consumption_water": [],
    }

    await setup_bridge({"energy": {"energy_sources": [SOLAR]}})

    assert manager.data["energy_sources"][0]["forecast_tilt"] == 30
    reason = report(hass, "energy").translation_placeholders["reason"]
    assert "energy_sources[0].forecast_tilt" in reason


@pytest.mark.usefixtures("energy")
async def test_report_only_lists_each_field(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    await setup_bridge({"energy": {"energy_sources": [SOLAR], "report_only": True}})

    manager = await async_get_manager(hass)
    assert manager.data is None
    changes = report(hass, "energy").translation_placeholders["changes"]
    assert (
        "energy_sources[0].stat_energy_from: unset → "
        "sensor.xcel_solar_current_summation_delivered_value"
    ) in changes


@pytest.mark.usefixtures("energy")
async def test_empty_yaml_with_nothing_saved_is_in_sync(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    await setup_bridge({"energy": {}})

    manager = await async_get_manager(hass)
    assert manager.data is None
    assert report(hass, "energy") is None


async def test_reports_when_energy_is_not_loaded(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    await setup_bridge({"energy": {"energy_sources": [SOLAR]}})

    reason = report(hass, "energy").translation_placeholders["reason"]
    assert "energy integration isn't loaded" in reason


@pytest.mark.usefixtures("energy")
async def test_export(
    hass: HomeAssistant, setup_bridge: SetupBridge, hass_ws_client: Any
) -> None:
    await save_in_ui(
        hass,
        hass_ws_client,
        energy_sources=[{**GRID_FROM_UI, "number_energy_price": 0.15}, SOLAR_FROM_UI],
    )
    await setup_bridge({})

    exported = await hass.services.async_call(
        "config_bridge", "export", blocking=True, return_response=True
    )

    assert exported["energy"] == {
        "energy_sources": [{**GRID, "number_energy_price": 0.15}, SOLAR]
    }
