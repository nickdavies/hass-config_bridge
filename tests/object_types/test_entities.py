"""Entities' model: the schema, rendering, and planning against the registry."""

from __future__ import annotations

from typing import Any

import probatio
import pytest

from custom_components.config_bridge.lib.claims import YAML_OWNER
from custom_components.config_bridge.lib.diff import FieldChange
from custom_components.config_bridge.object_types.entities.model import (
    DEFAULTS,
    SCHEMA,
    LiveEntity,
    export_item,
    missing_references,
    plan_entities,
    render,
)


def live(entity_id: str, registry_id: str, **fields: Any) -> LiveEntity:
    return LiveEntity(registry_id, entity_id, {**DEFAULTS, **fields})


def yaml(**items: dict[str, Any]) -> dict[str, tuple[str, dict[str, Any]]]:
    return {
        entity_id.replace("__", "."): (YAML_OWNER, render(item))
        for entity_id, item in items.items()
    }


class TestSchema:
    def test_an_item_with_nothing_under_it_pins_the_defaults(self) -> None:
        assert SCHEMA({"items": {"light.a": None}}) == {"items": {"light.a": {}}}

    def test_fields(self) -> None:
        item = SCHEMA(
            {
                "items": {
                    "Light.A": {
                        "area_id": "kitchen",
                        "name": "Counter",
                        "icon": "mdi:lamp",
                        "aliases": "counter lights",
                        "labels": ["downstairs"],
                        "hidden": True,
                        "disabled": False,
                    }
                }
            }
        )["items"]["light.a"]
        assert item["aliases"] == ["counter lights"]
        assert item["hidden"] is True

    def test_an_unknown_field_is_a_typo(self) -> None:
        with pytest.raises(probatio.Invalid):
            SCHEMA({"items": {"light.a": {"area": "kitchen"}}})

    def test_area_id_is_an_id(self) -> None:
        with pytest.raises(probatio.Invalid):
            SCHEMA({"items": {"light.a": {"area_id": "Living Room"}}})


def test_render_fills_every_field() -> None:
    assert render({"aliases": ["b", "a", "b"], "hidden": True}) == {
        "area_id": None,
        "name": None,
        "icon": None,
        "device_class": None,
        "aliases": ["a", "b"],
        "name_is_alias": True,
        "labels": [],
        "hidden": True,
        "disabled": False,
    }


def test_export_leaves_out_defaults() -> None:
    assert export_item(DEFAULTS) is None
    assert export_item({**DEFAULTS, "area_id": "kitchen", "device_class": "door"}) == {
        "area_id": "kitchen"
    }


class TestPlan:
    def test_in_sync(self) -> None:
        plan = plan_entities(
            yaml(light__a={"area_id": "kitchen"}),
            {"light.a": live("light.a", "r1", area_id="kitchen")},
            {},
        )
        assert plan.changes == ()
        assert plan.owned_after == {"light.a": "r1"}

    def test_fields_left_out_go_back_to_the_integrations_own(self) -> None:
        plan = plan_entities(
            yaml(light__a={"area_id": "kitchen"}),
            {"light.a": live("light.a", "r1", name="Mine", hidden=True)},
            {},
        )
        (change,) = plan.changes
        assert change.fields == {**DEFAULTS, "area_id": "kitchen"}
        assert change.changes == (
            FieldChange("area_id", None, "kitchen"),
            FieldChange("hidden", True, False),
            FieldChange("name", "Mine", None),
        )

    def test_a_renamed_entity_is_found_by_registry_id_and_renamed_back(self) -> None:
        plan = plan_entities(
            yaml(light__a={}),
            {"light.renamed": live("light.renamed", "r1")},
            {"light.a": "r1"},
        )
        (change,) = plan.changes
        assert change.current_entity_id == "light.renamed"
        assert change.changes == (FieldChange("entity_id", "light.renamed", "light.a"),)
        assert plan.owned_after == {"light.a": "r1"}

    def test_a_rename_back_onto_an_id_since_taken_is_a_problem(self) -> None:
        plan = plan_entities(
            yaml(light__a={}),
            {
                "light.renamed": live("light.renamed", "r1"),
                "light.a": live("light.a", "r2"),
            },
            {"light.a": "r1"},
        )
        assert plan.changes == ()
        assert "another entity has since taken its id" in plan.problems[0]

    def test_an_unregistered_entity_is_a_problem(self) -> None:
        plan = plan_entities(yaml(light__a={}), {}, {})
        assert plan.problems == ("light.a: no such entity in the entity registry",)

    def test_an_entity_no_longer_listed_is_released_once(self) -> None:
        plan = plan_entities(
            {},
            {"light.a": live("light.a", "r1", area_id="kitchen")},
            {"light.a": "r1"},
        )
        (change,) = plan.changes
        assert change.owner is None
        assert change.fields == DEFAULTS
        assert change.summary.startswith("Release light.a")
        assert plan.owned_after == {}

    def test_releasing_an_entity_already_at_its_own_values_writes_nothing(
        self,
    ) -> None:
        plan = plan_entities({}, {"light.a": live("light.a", "r1")}, {"light.a": "r1"})
        assert plan.changes == ()

    def test_a_released_entity_gone_from_the_registry_is_dropped(self) -> None:
        plan = plan_entities({}, {}, {"light.a": "r1"})
        assert plan.changes == ()
        assert plan.problems == ()

    def test_a_claimed_entity_says_who_claimed_it(self) -> None:
        plan = plan_entities(
            {"switch.k": ("lights", render({"area_id": "kitchen"}))},
            {"switch.k": live("switch.k", "r1")},
            {},
        )
        assert plan.changes[0].summary == "Pin switch.k (claimed by lights)"


def test_missing_areas_and_labels() -> None:
    desired = {
        **yaml(light__a={"area_id": "attic", "labels": ["up", "down"]}),
        "switch.k": ("lights", render({"area_id": "cellar"})),
    }
    assert missing_references(desired, {"kitchen"}, {"down"}) == [
        "light.a: area 'attic' doesn't exist",
        "light.a: label 'up' doesn't exist",
        "switch.k (claimed by lights): area 'cellar' doesn't exist",
    ]
