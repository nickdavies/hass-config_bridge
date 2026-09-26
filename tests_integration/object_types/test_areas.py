"""Areas against Home Assistant's real area, floor and label registries."""

from __future__ import annotations

from typing import Any

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    floor_registry as fr,
    label_registry as lr,
)

from ..conftest import SetupBridge, ledger_storage, report


def areas(hass: HomeAssistant) -> dict[str, ar.AreaEntry]:
    return {area.id: area for area in ar.async_get(hass).async_list_areas()}


async def test_exclusive_makes_the_registry_exactly_the_yaml(
    hass: HomeAssistant, setup_bridge: SetupBridge, hass_storage: dict[str, Any]
) -> None:
    registry = ar.async_get(hass)
    registry.async_create("Kitchen")
    registry.async_create("Garage")

    await setup_bridge(
        {
            "areas": {
                "mode": "exclusive",
                "items": {
                    "kitchen": {"name": "Kitchen", "icon": "mdi:stove"},
                    # Key and name deliberately different: the id is the key.
                    "lounge": {"name": "Living Room", "aliases": ["family room"]},
                },
            }
        }
    )

    live = areas(hass)
    assert set(live) == {"kitchen", "lounge"}
    assert live["kitchen"].icon == "mdi:stove"
    assert live["lounge"].name == "Living Room"
    assert live["lounge"].aliases == {"family room"}
    assert hass_storage["config_bridge"]["data"]["areas"]["owned"] == [
        "kitchen",
        "lounge",
    ]
    assert report(hass, "areas") is None


async def test_fields_the_yaml_leaves_out_are_cleared(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    ar.async_get(hass).async_create("Kitchen", icon="mdi:stove", aliases={"cook"})

    await setup_bridge(
        {"areas": {"mode": "owned", "items": {"kitchen": {"name": "Kitchen"}}}}
    )

    kitchen = areas(hass)["kitchen"]
    assert kitchen.icon is None
    assert kitchen.aliases == set()


async def test_owned_deletes_only_what_it_owned(
    hass: HomeAssistant, setup_bridge: SetupBridge, hass_storage: dict[str, Any]
) -> None:
    registry = ar.async_get(hass)
    registry.async_create("Garage")  # listed last boot, dropped from the YAML since
    registry.async_create("Shed")  # made in the UI, never listed
    hass_storage["config_bridge"] = ledger_storage({"areas": {"owned": ["garage"]}})

    await setup_bridge(
        {"areas": {"mode": "owned", "items": {"kitchen": {"name": "Kitchen"}}}}
    )

    assert set(areas(hass)) == {"kitchen", "shed"}


async def test_floor_and_label_references(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    fr.async_get(hass).async_create("Ground")
    lr.async_get(hass).async_create("Downstairs")
    hass.states.async_set(
        "sensor.kitchen_temperature", "21.5", {"device_class": "temperature"}
    )

    await setup_bridge(
        {
            "areas": {
                "mode": "owned",
                "items": {
                    "kitchen": {
                        "name": "Kitchen",
                        "floor_id": "ground",
                        "labels": ["downstairs"],
                        "temperature_entity_id": "sensor.kitchen_temperature",
                    }
                },
            }
        }
    )

    kitchen = areas(hass)["kitchen"]
    assert kitchen.floor_id == "ground"
    assert kitchen.labels == {"downstairs"}
    assert kitchen.temperature_entity_id == "sensor.kitchen_temperature"


async def test_bad_references_are_reported_before_anything_is_written(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    hass.states.async_set("sensor.kitchen_humidity", "40", {"device_class": "humidity"})

    await setup_bridge(
        {
            "areas": {
                "mode": "owned",
                "items": {
                    "kitchen": {"name": "Kitchen", "floor_id": "ground"},
                    "lounge": {
                        "name": "Lounge",
                        "temperature_entity_id": "sensor.kitchen_humidity",
                    },
                },
            }
        }
    )

    assert areas(hass) == {}
    reason = report(hass, "areas").translation_placeholders["reason"]
    assert "floor 'ground' doesn't exist" in reason
    assert "sensor.kitchen_humidity is not a temperature sensor" in reason


async def test_a_name_held_by_an_unmanaged_area_is_reported(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    ar.async_get(hass).async_create("Living Room")

    await setup_bridge(
        {"areas": {"mode": "owned", "items": {"lounge": {"name": "Living Room"}}}}
    )

    assert set(areas(hass)) == {"living_room"}
    assert (
        "belongs to area 'living_room'"
        in (report(hass, "areas").translation_placeholders["reason"])
    )


async def test_exclusive_with_nothing_listed_is_refused(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    ar.async_get(hass).async_create("Kitchen")

    await setup_bridge({"areas": {"mode": "exclusive"}})

    assert set(areas(hass)) == {"kitchen"}
    assert report(hass, "areas") is not None


async def test_waits_for_home_assistant_to_start(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    hass.set_state(CoreState.starting)

    await setup_bridge(
        {"areas": {"mode": "owned", "items": {"kitchen": {"name": "Kitchen"}}}}
    )
    assert areas(hass) == {}

    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    assert set(areas(hass)) == {"kitchen"}


async def test_report_only_records_no_ownership(
    hass: HomeAssistant, setup_bridge: SetupBridge, hass_storage: dict[str, Any]
) -> None:
    ar.async_get(hass).async_create("Kitchen")

    await setup_bridge(
        {
            "areas": {
                "mode": "owned",
                "report_only": True,
                "items": {"kitchen": {"name": "Kitchen"}},
            }
        }
    )

    # In sync, so nothing to report; but report-only writes nothing at all,
    # the ledger included.
    assert report(hass, "areas") is None
    assert "config_bridge" not in hass_storage
