"""Devices against Home Assistant's real device, area and label registries."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    label_registry as lr,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.config_bridge import claim_devices

from ..conftest import SetupBridge, ledger_storage, report

Z = "zigbee2mqtt_0x001788010c6f92e4"


def register(hass: HomeAssistant, identifier: str = Z) -> dr.DeviceEntry:
    entry = MockConfigEntry(domain="mqtt")
    entry.add_to_hass(hass)
    return dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("mqtt", identifier)},
        name="0x001788010c6f92e4",
    )


def device(hass: HomeAssistant, identifier: str = Z) -> dr.DeviceEntry:
    (found,) = dr.async_get(hass).async_get_devices(identifiers={("mqtt", identifier)})
    return found


async def test_listed_fields_are_set_and_the_rest_put_back(
    hass: HomeAssistant, setup_bridge: SetupBridge, hass_storage: dict[str, Any]
) -> None:
    ar.async_get(hass).async_create("Dining")
    lr.async_get(hass).async_create("Lights")
    registered = register(hass)
    dr.async_get(hass).async_update_device(
        registered.id, disabled_by=dr.DeviceEntryDisabler.USER
    )

    await setup_bridge(
        {
            "devices": {
                "items": {
                    "mqtt": {
                        Z: {
                            "area_id": "dining",
                            "name": "Centre 1",
                            "labels": ["lights"],
                        }
                    }
                }
            }
        }
    )

    pinned = device(hass)
    assert pinned.area_id == "dining"
    assert pinned.name_by_user == "Centre 1"
    assert pinned.labels == {"lights"}
    assert pinned.disabled_by is None
    assert hass_storage["config_bridge"]["data"]["devices"]["owned"] == [["mqtt", Z]]
    assert report(hass, "devices") is None


async def test_a_devices_entities_follow_its_area(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    ar.async_get(hass).async_create("Dining")
    registered = register(hass)
    light = er.async_get(hass).async_get_or_create(
        "light", "mqtt", Z, device_id=registered.id
    )

    await setup_bridge({"devices": {"items": {"mqtt": {Z: {"area_id": "dining"}}}}})

    # Its own area stays unset (pinned so by `entities` if listed); the
    # device's applies.
    assert er.async_get(hass).async_get(light.entity_id).area_id is None
    assert device(hass).area_id == "dining"


async def test_a_claim_is_pinned_without_any_yaml(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    ar.async_get(hass).async_create("Dining")
    register(hass)
    claim_devices(hass, "plants", {"mqtt": {Z: {"area_id": "dining"}}})

    await setup_bridge({})

    assert device(hass).area_id == "dining"


async def test_a_device_no_longer_listed_is_released(
    hass: HomeAssistant, setup_bridge: SetupBridge, hass_storage: dict[str, Any]
) -> None:
    ar.async_get(hass).async_create("Dining")
    registered = register(hass)
    dr.async_get(hass).async_update_device(registered.id, area_id="dining")
    hass_storage["config_bridge"] = ledger_storage(
        {"devices": {"owned": [["mqtt", Z]]}}
    )

    await setup_bridge({})

    assert device(hass).area_id is None
    assert "devices" not in hass_storage["config_bridge"]["data"]


async def test_what_an_integration_disabled_stays_disabled(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    registered = register(hass)
    dr.async_get(hass).async_update_device(
        registered.id, disabled_by=dr.DeviceEntryDisabler.INTEGRATION
    )

    await setup_bridge({"devices": {"items": {"mqtt": {Z: None}}}})

    assert device(hass).disabled_by is dr.DeviceEntryDisabler.INTEGRATION


async def test_missing_devices_and_double_listings_are_reported(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    ar.async_get(hass).async_create("Dining")
    register(hass)
    claim_devices(hass, "plants", {"mqtt": {Z: None}})

    await setup_bridge(
        {"devices": {"items": {"mqtt": {Z: {"area_id": "dining"}, "gone": None}}}}
    )

    reason = report(hass, "devices").translation_placeholders["reason"]
    assert f"mqtt {Z} is listed by the YAML and plants" in reason
    assert "device mqtt gone: no such device in the device registry" in reason
    assert device(hass).area_id is None


async def test_an_identifier_two_devices_share_is_reported(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    register(hass)
    register(hass)  # the same identifier, under a second config entry

    await setup_bridge({"devices": {"items": {"mqtt": {Z: None}}}})

    reason = report(hass, "devices").translation_placeholders["reason"]
    assert f"device mqtt {Z}: 2 devices have this identifier" in reason


async def test_export_lists_devices_with_anything_set(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    ar.async_get(hass).async_create("Dining")
    registered = register(hass)
    register(hass, "zigbee2mqtt_other")
    dr.async_get(hass).async_update_device(registered.id, area_id="dining")

    await setup_bridge({})
    exported = await hass.services.async_call(
        "config_bridge", "export", {}, blocking=True, return_response=True
    )

    assert exported["devices"] == {"items": {"mqtt": {Z: {"area_id": "dining"}}}}
