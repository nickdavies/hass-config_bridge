"""Entity areas against Home Assistant's real entity and area registries."""

from __future__ import annotations

from typing import Any

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers import area_registry as ar, entity_registry as er

from ..conftest import SetupBridge, ledger_storage, report


def entity(hass: HomeAssistant, object_id: str) -> str:
    """Register `light.<object_id>` as an integration would."""
    entry = er.async_get(hass).async_get_or_create(
        "light", "test", object_id, suggested_object_id=object_id
    )
    return entry.entity_id


def area_of(hass: HomeAssistant, entity_id: str) -> str | None:
    entry = er.async_get(hass).async_get(entity_id)
    assert entry is not None
    return entry.area_id


async def test_puts_listed_entities_in_their_areas(
    hass: HomeAssistant, setup_bridge: SetupBridge, hass_storage: dict[str, Any]
) -> None:
    ar.async_get(hass).async_create("Kitchen")
    ar.async_get(hass).async_create("Dining")
    kitchen, dining = entity(hass, "kitchen_all"), entity(hass, "dining_all")

    await setup_bridge(
        {"entity_areas": {"items": {kitchen: "kitchen", dining: "dining"}}}
    )

    assert area_of(hass, kitchen) == "kitchen"
    assert area_of(hass, dining) == "dining"
    assert hass_storage["config_bridge"]["data"]["entity_areas"]["owned"] == [
        dining,
        kitchen,
    ]
    assert report(hass, "entity_areas") is None


async def test_moves_an_entity_from_the_area_it_was_given_in_the_ui(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    ar.async_get(hass).async_create("Kitchen")
    ar.async_get(hass).async_create("Dining")
    lamp = entity(hass, "lamp")
    er.async_get(hass).async_update_entity(lamp, area_id="dining")

    await setup_bridge({"entity_areas": {"items": {lamp: "kitchen"}}})

    assert area_of(hass, lamp) == "kitchen"


async def test_clears_only_entities_it_owned(
    hass: HomeAssistant, setup_bridge: SetupBridge, hass_storage: dict[str, Any]
) -> None:
    ar.async_get(hass).async_create("Kitchen")
    dropped, ui_only = entity(hass, "dropped"), entity(hass, "ui_only")
    registry = er.async_get(hass)
    registry.async_update_entity(dropped, area_id="kitchen")  # listed last boot
    registry.async_update_entity(ui_only, area_id="kitchen")  # never listed
    hass_storage["config_bridge"] = ledger_storage(
        {"entity_areas": {"owned": [dropped]}}
    )

    await setup_bridge({"entity_areas": {"items": {}}})

    assert area_of(hass, dropped) is None
    assert area_of(hass, ui_only) == "kitchen"
    assert hass_storage["config_bridge"]["data"]["entity_areas"]["owned"] == []


async def test_a_missing_entity_or_area_is_reported_and_nothing_is_written(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    ar.async_get(hass).async_create("Kitchen")
    lamp = entity(hass, "lamp")

    await setup_bridge(
        {
            "entity_areas": {
                "items": {
                    lamp: "kitchen",
                    "light.not_discovered_yet": "kitchen",
                    entity(hass, "attic_lamp"): "attic",
                }
            }
        }
    )

    issue = report(hass, "entity_areas")
    assert issue is not None
    reason = str(issue.translation_placeholders)
    assert "light.not_discovered_yet: no such entity" in reason
    assert "area 'attic' doesn't exist" in reason
    assert area_of(hass, lamp) is None


async def test_in_sync_writes_nothing_and_raises_nothing(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    ar.async_get(hass).async_create("Kitchen")
    lamp = entity(hass, "lamp")
    er.async_get(hass).async_update_entity(lamp, area_id="kitchen")

    await setup_bridge({"entity_areas": {"items": {lamp: "kitchen"}}})

    assert area_of(hass, lamp) == "kitchen"
    assert report(hass, "entity_areas") is None


async def test_areas_made_on_the_same_boot_are_there_first(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    """Both run once Home Assistant has started. entity_areas is listed first
    here, as a package merge might put it; it still runs after areas."""
    lamp = entity(hass, "lamp")
    hass.set_state(CoreState.starting)

    await setup_bridge(
        {
            "entity_areas": {"items": {lamp: "kitchen"}},
            "areas": {"mode": "owned", "items": {"kitchen": {"name": "Kitchen"}}},
        }
    )
    assert area_of(hass, lamp) is None  # nothing before Home Assistant starts

    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()

    assert area_of(hass, lamp) == "kitchen"
    assert report(hass, "entity_areas") is None


async def test_export_lists_entities_with_an_area_of_their_own(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    ar.async_get(hass).async_create("Kitchen")
    lamp = entity(hass, "lamp")
    entity(hass, "no_area")
    er.async_get(hass).async_update_entity(lamp, area_id="kitchen")
    await setup_bridge({})

    exported = await hass.services.async_call(
        "config_bridge", "export", blocking=True, return_response=True
    )

    assert exported["entity_areas"] == {"items": {lamp: "kitchen"}}
