"""What holds across object types: the error boundaries, the issues, the export."""

from __future__ import annotations

import sys
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import issue_registry as ir
from homeassistant.loader import DATA_CUSTOM_COMPONENTS
from homeassistant.setup import async_setup_component

from custom_components.config_bridge.object_types.http.kind import HttpKind

from .conftest import DOMAIN, SetupBridge, _ensure_custom_components_path, report

AREAS = {"mode": "owned", "items": {"kitchen": {"name": "Kitchen"}}}
HTTP = {"use_x_forwarded_for": True, "trusted_proxies": ["10.244.0.0/16"]}


async def test_an_object_type_whose_ha_moved_under_it_does_not_stop_the_others(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    with patch("homeassistant.components.http.config.STORAGE_VERSION", 3):
        await setup_bridge({"http": HTTP, "areas": AREAS})

    assert report(hass, "http") is not None
    assert report(hass, "areas") is None
    assert "kitchen" in {area.id for area in ar.async_get(hass).async_list_areas()}


async def test_an_unexpected_error_is_contained_too(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    with patch.object(HttpKind, "async_plan", side_effect=KeyError("stable")):
        await setup_bridge({"http": HTTP, "areas": AREAS})

    reason = report(hass, "http").translation_placeholders["reason"]
    assert "KeyError" in reason
    assert report(hass, "areas") is None


async def test_a_kind_that_fails_to_import_does_not_stop_the_others(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    # None in sys.modules makes the import raise ImportError.
    with patch.dict(
        sys.modules, {"custom_components.config_bridge.object_types.http.kind": None}
    ):
        await setup_bridge({"http": HTTP, "areas": AREAS})

    reason = report(hass, "http").translation_placeholders["reason"]
    assert "while importing its Kind" in reason
    assert "object_types.http.kind" in reason
    assert report(hass, "areas") is None
    assert "kitchen" in {area.id for area in ar.async_get(hass).async_list_areas()}


async def test_an_object_type_back_in_sync_clears_its_issue(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    ir.async_create_issue(
        hass,
        DOMAIN,
        "report_areas",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="report",
    )

    await setup_bridge({"areas": AREAS})

    assert report(hass, "areas") is None


async def test_an_object_type_taken_out_of_the_yaml_clears_its_issue(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    ir.async_create_issue(
        hass,
        DOMAIN,
        "report_mqtt",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="report",
    )

    await setup_bridge({"areas": AREAS})

    assert report(hass, "mqtt") is None


async def test_bad_yaml_fails_setup_so_check_config_catches_it(
    hass: HomeAssistant,
) -> None:
    hass.data.pop(DATA_CUSTOM_COMPONENTS, None)
    _ensure_custom_components_path()

    assert not await async_setup_component(
        hass, DOMAIN, {DOMAIN: {"http": {"trusted_proxies": ["10.244.0.1/16"]}}}
    )


async def test_export_returns_every_object_type_in_yaml_shape(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    ar.async_get(hass).async_create("Kitchen", icon="mdi:stove")

    await setup_bridge({})
    exported = await hass.services.async_call(
        DOMAIN, "export", {}, blocking=True, return_response=True
    )

    assert set(exported) == {"http", "mqtt", "network", "areas"}
    assert exported["areas"] == {
        "mode": "exclusive",
        "items": {"kitchen": {"name": "Kitchen", "icon": "mdi:stove"}},
    }
    assert exported["mqtt"] == {}
    assert exported["http"] == {}
    assert exported["network"]["adapters"] == []
