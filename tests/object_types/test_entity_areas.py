"""Entity areas' model: the YAML's schema, and the checks before any write."""

from __future__ import annotations

import probatio
import pytest

from custom_components.config_bridge.object_types.entity_areas.model import (
    SCHEMA,
    export,
    missing_references,
    render,
)


def test_items_map_entities_to_area_ids() -> None:
    assert SCHEMA({"items": {"light.kitchen_all": "kitchen"}}) == {
        "items": {"light.kitchen_all": "kitchen"}
    }


def test_no_items_is_none_managed() -> None:
    assert SCHEMA({}) == {"items": {}}


def test_entity_ids_are_lowercased_as_home_assistant_does() -> None:
    assert SCHEMA({"items": {"Light.Kitchen_All": "kitchen"}})["items"] == {
        "light.kitchen_all": "kitchen"
    }


def test_two_spellings_of_one_entity_are_refused() -> None:
    with pytest.raises(probatio.Invalid, match="listed twice"):
        SCHEMA({"items": {"light.kitchen": "kitchen", "Light.Kitchen": "dining"}})


@pytest.mark.parametrize(
    "items",
    [
        {"not_an_entity": "kitchen"},
        {"light.kitchen": "Kitchen"},  # an area id, not a name
        {"light.kitchen": ["kitchen"]},
    ],
)
def test_bad_items_are_refused(items: dict) -> None:
    with pytest.raises(probatio.Invalid):
        SCHEMA({"items": items})


def test_render_is_one_field_per_entity() -> None:
    assert render({"light.a": "kitchen"}) == {"light.a": {"area_id": "kitchen"}}


def test_missing_entities_and_areas_are_all_named() -> None:
    desired = render(
        {"light.a": "kitchen", "light.b": "attic", "light.gone": "kitchen"}
    )
    assert missing_references(
        desired, entities={"light.a", "light.b"}, areas={"kitchen"}
    ) == [
        "light.b: area 'attic' doesn't exist",
        "light.gone: no such entity in the entity registry",
    ]


def test_nothing_missing() -> None:
    desired = render({"light.a": "kitchen"})
    assert missing_references(desired, entities={"light.a"}, areas={"kitchen"}) == []


def test_export_lists_only_entities_with_an_area_of_their_own() -> None:
    assert export({"light.b": "kitchen", "light.a": None, "light.c": "dining"}) == {
        "items": {"light.b": "kitchen", "light.c": "dining"}
    }
