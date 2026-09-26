"""Devices' model: the schema, rendering, and planning against the registry."""

from __future__ import annotations

from typing import Any

import probatio
import pytest

from custom_components.config_bridge.lib.claims import YAML_OWNER
from custom_components.config_bridge.lib.diff import FieldChange
from custom_components.config_bridge.object_types.devices.model import (
    DEFAULTS,
    SCHEMA,
    LiveDevice,
    export_item,
    flatten,
    missing_references,
    plan_devices,
    render,
)

Z = ("mqtt", "zigbee2mqtt_0x01")


def live(registry_id: str, **fields: Any) -> LiveDevice:
    return LiveDevice(registry_id, {**DEFAULTS, **fields})


class TestSchema:
    def test_items_nest_by_domain_then_identifier(self) -> None:
        assert SCHEMA(
            {"items": {"mqtt": {"zigbee2mqtt_0x01": {"area_id": "dining"}, "b": None}}}
        ) == {"items": {"mqtt": {"zigbee2mqtt_0x01": {"area_id": "dining"}, "b": {}}}}

    def test_an_unknown_field_points_at_its_device(self) -> None:
        with pytest.raises(probatio.Invalid) as err:
            SCHEMA({"items": {"mqtt": {"a": {"icon": "mdi:x"}}}})
        assert err.value.path[:3] == ["items", "mqtt", "a"]

    def test_the_domain_is_an_id(self) -> None:
        with pytest.raises(probatio.Invalid):
            SCHEMA({"items": {"Zigbee MQTT": {"a": None}}})


def test_flatten() -> None:
    assert flatten({"mqtt": {"a": 1, "b": 2}, "hue": {"c": 3}}) == {
        ("mqtt", "a"): 1,
        ("mqtt", "b"): 2,
        ("hue", "c"): 3,
    }


def test_render_and_export() -> None:
    fields = render({"area_id": "dining", "labels": ["b", "a"]})
    assert fields == {
        "area_id": "dining",
        "name": None,
        "labels": ["a", "b"],
        "disabled": False,
    }
    assert export_item(fields) == {"area_id": "dining", "labels": ["a", "b"]}
    assert export_item(DEFAULTS) is None


class TestPlan:
    def test_fields_left_out_go_back_to_their_defaults(self) -> None:
        plan = plan_devices(
            {Z: (YAML_OWNER, render({"area_id": "dining"}))},
            {Z: live("d1", name="Mine")},
            set(),
        )
        (change,) = plan.changes
        assert change.registry_id == "d1"
        assert change.changes == (
            FieldChange("area_id", None, "dining"),
            FieldChange("name", "Mine", None),
        )
        assert change.summary == "Pin device mqtt zigbee2mqtt_0x01"
        assert plan.owned_after == (Z,)

    def test_in_sync(self) -> None:
        plan = plan_devices({Z: (YAML_OWNER, DEFAULTS)}, {Z: live("d1")}, set())
        assert plan.changes == ()

    def test_an_unregistered_device_is_a_problem(self) -> None:
        plan = plan_devices({Z: ("plants", DEFAULTS)}, {}, set())
        assert plan.problems == (
            "device mqtt zigbee2mqtt_0x01 (claimed by plants): no such device in "
            "the device registry",
        )
        assert plan.owned_after == ()

    def test_a_device_no_longer_listed_is_released(self) -> None:
        plan = plan_devices({}, {Z: live("d1", area_id="dining")}, {Z})
        (change,) = plan.changes
        assert change.owner is None
        assert change.fields == DEFAULTS
        assert plan.owned_after == ()


def test_missing_areas_and_labels() -> None:
    desired = {Z: ("plants", render({"area_id": "attic", "labels": ["up"]}))}
    assert missing_references(desired, set(), set()) == [
        "device mqtt zigbee2mqtt_0x01 (claimed by plants): area 'attic' doesn't exist",
        "device mqtt zigbee2mqtt_0x01 (claimed by plants): label 'up' doesn't exist",
    ]
