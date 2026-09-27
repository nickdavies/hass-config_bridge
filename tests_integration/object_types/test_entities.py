"""Entities against Home Assistant's real entity, area and label registries."""

from __future__ import annotations

from typing import Any

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    entity_registry as er,
    label_registry as lr,
)

from custom_components.config_bridge import claim_entities

from ..conftest import SetupBridge, ledger_storage, report


def register(hass: HomeAssistant, entity_id: str) -> er.RegistryEntry:
    domain, object_id = entity_id.split(".")
    return er.async_get(hass).async_get_or_create(
        domain, "test", object_id, suggested_object_id=object_id
    )


def entry(hass: HomeAssistant, entity_id: str) -> er.RegistryEntry | None:
    return er.async_get(hass).async_get(entity_id)


def owned(hass_storage: dict[str, Any]) -> dict[str, str]:
    return hass_storage["config_bridge"]["data"]["entities"]["owned"]


async def test_listed_fields_are_set_and_the_rest_put_back(
    hass: HomeAssistant, setup_bridge: SetupBridge, hass_storage: dict[str, Any]
) -> None:
    ar.async_get(hass).async_create("Kitchen")
    lr.async_get(hass).async_create("Downstairs")
    light = register(hass, "light.a")
    er.async_get(hass).async_update_entity(
        "light.a", name="Renamed in the UI", icon="mdi:lamp", aliases=["counter"]
    )

    await setup_bridge(
        {
            "entities": {
                "items": {
                    "light.a": {
                        "area_id": "kitchen",
                        "labels": ["downstairs"],
                        "aliases": ["worktop"],
                    }
                }
            }
        }
    )

    pinned = entry(hass, "light.a")
    assert pinned.area_id == "kitchen"
    assert pinned.labels == {"downstairs"}
    assert pinned.name is None
    assert pinned.icon is None
    assert pinned.aliases == [er.COMPUTED_NAME, "worktop"]
    assert owned(hass_storage) == {"light.a": light.id}
    assert report(hass, "entities") is None


async def test_a_claim_is_pinned_without_any_yaml(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    ar.async_get(hass).async_create("Kitchen")
    register(hass, "switch.k")
    claim_entities(hass, "lights", {"switch.k": {"area_id": "kitchen"}})

    await setup_bridge({})

    assert entry(hass, "switch.k").area_id == "kitchen"
    assert report(hass, "entities") is None


async def test_an_entity_renamed_in_the_ui_is_renamed_back(
    hass: HomeAssistant, setup_bridge: SetupBridge, hass_storage: dict[str, Any]
) -> None:
    light = register(hass, "light.a")
    hass_storage["config_bridge"] = ledger_storage(
        {"entities": {"owned": {"light.a": light.id}}}
    )
    er.async_get(hass).async_update_entity("light.a", new_entity_id="light.b")

    await setup_bridge({"entities": {"items": {"light.a": None}}})

    assert entry(hass, "light.a").id == light.id
    assert entry(hass, "light.b") is None


async def test_an_entity_no_longer_listed_is_released(
    hass: HomeAssistant, setup_bridge: SetupBridge, hass_storage: dict[str, Any]
) -> None:
    ar.async_get(hass).async_create("Kitchen")
    light = register(hass, "light.a")
    er.async_get(hass).async_update_entity("light.a", area_id="kitchen")
    hass_storage["config_bridge"] = ledger_storage(
        {"entities": {"owned": {"light.a": light.id}}}
    )

    await setup_bridge({})

    assert entry(hass, "light.a").area_id is None
    assert "entities" not in hass_storage["config_bridge"]["data"]


async def test_entities_never_listed_are_left_alone(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    register(hass, "light.a")
    er.async_get(hass).async_update_entity("light.a", name="Mine")

    await setup_bridge({"entities": {"items": {}}})

    assert entry(hass, "light.a").name == "Mine"


async def test_what_an_integration_hid_stays_hidden(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    register(hass, "sensor.a")
    register(hass, "sensor.b")
    registry = er.async_get(hass)
    registry.async_update_entity(
        "sensor.a", hidden_by=er.RegistryEntryHider.INTEGRATION
    )
    registry.async_update_entity("sensor.b", hidden_by=er.RegistryEntryHider.USER)

    await setup_bridge({"entities": {"items": {"sensor.a": None, "sensor.b": None}}})

    assert entry(hass, "sensor.a").hidden_by is er.RegistryEntryHider.INTEGRATION
    assert entry(hass, "sensor.b").hidden_by is None


async def test_hidden_and_disabled_are_set_by_the_user(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    register(hass, "sensor.a")

    await setup_bridge(
        {"entities": {"items": {"sensor.a": {"hidden": True, "disabled": True}}}}
    )

    pinned = entry(hass, "sensor.a")
    assert pinned.hidden_by is er.RegistryEntryHider.USER
    assert pinned.disabled_by is er.RegistryEntryDisabler.USER


async def test_an_entity_listed_twice_reports_and_writes_nothing(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    ar.async_get(hass).async_create("Kitchen")
    register(hass, "switch.k")
    register(hass, "light.a")
    claim_entities(hass, "lights", {"switch.k": {"area_id": "kitchen"}})

    await setup_bridge(
        {"entities": {"items": {"switch.k": None, "light.a": {"area_id": "kitchen"}}}}
    )

    issue = report(hass, "entities")
    assert (
        "switch.k is listed by the YAML and lights"
        in (issue.translation_placeholders["reason"])
    )
    assert entry(hass, "light.a").area_id is None


async def test_missing_entities_and_areas_are_reported(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    register(hass, "switch.k")
    claim_entities(hass, "lights", {"switch.k": {"area_id": "attic"}})

    await setup_bridge({"entities": {"items": {"light.gone": None}}})

    reason = report(hass, "entities").translation_placeholders["reason"]
    assert "switch.k (claimed by lights): area 'attic' doesn't exist" in reason
    assert "light.gone: no such entity in the entity registry" in reason


async def test_runs_after_areas_so_a_new_area_can_be_used(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    hass.set_state(CoreState.starting)
    register(hass, "light.a")

    await setup_bridge(
        {
            # Listed first on purpose: the registry's order decides.
            "entities": {"items": {"light.a": {"area_id": "kitchen"}}},
            "areas": {"mode": "owned", "items": {"kitchen": {"name": "Kitchen"}}},
        }
    )
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()

    assert entry(hass, "light.a").area_id == "kitchen"
    assert report(hass, "entities") is None


async def test_a_claim_made_after_the_bridge_set_up_is_still_applied(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    # Integrations set up in any order before Home Assistant has started.
    hass.set_state(CoreState.starting)
    ar.async_get(hass).async_create("Kitchen")
    register(hass, "switch.k")

    await setup_bridge({})
    claim_entities(hass, "lights", {"switch.k": {"area_id": "kitchen"}})
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()

    assert entry(hass, "switch.k").area_id == "kitchen"


async def test_export_lists_entities_with_anything_set(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    ar.async_get(hass).async_create("Kitchen")
    register(hass, "light.a")
    register(hass, "light.b")
    er.async_get(hass).async_update_entity("light.a", area_id="kitchen")

    await setup_bridge({})
    exported = await hass.services.async_call(
        "config_bridge", "export", {}, blocking=True, return_response=True
    )

    assert exported["entities"] == {"items": {"light.a": {"area_id": "kitchen"}}}
