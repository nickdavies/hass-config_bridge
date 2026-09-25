from __future__ import annotations

from custom_components.config_bridge.model.areas import (
    duplicate_names,
    export_area,
    name_conflicts,
    render_area,
)


def test_render_fills_every_field() -> None:
    assert render_area(
        {"name": "Kitchen", "aliases": ["cook", "cook"], "labels": []}
    ) == {
        "name": "Kitchen",
        "icon": None,
        "floor_id": None,
        "aliases": ["cook"],
        "labels": [],
        "picture": None,
        "temperature_entity_id": None,
        "humidity_entity_id": None,
    }


def test_duplicate_names_ignore_case_and_spaces() -> None:
    items = {
        "lounge": {"name": "Living Room"},
        "living_room": {"name": "livingroom"},
        "kitchen": {"name": "Kitchen"},
    }
    assert duplicate_names(items) == [("living_room", "lounge")]


def test_name_held_by_another_area_conflicts() -> None:
    desired = {"lounge": {"name": "Living Room"}}
    live = {"living_room": {"name": "living room"}}
    assert name_conflicts(desired, live, deleting=set()) == [
        "lounge: the name 'Living Room' belongs to area 'living_room'"
    ]


def test_name_freed_by_a_delete_does_not_conflict() -> None:
    desired = {"lounge": {"name": "Living Room"}}
    live = {"living_room": {"name": "Living Room"}}
    assert name_conflicts(desired, live, deleting={"living_room"}) == []


def test_an_area_keeps_its_own_name() -> None:
    desired = {"lounge": {"name": "Lounge"}}
    assert name_conflicts(desired, {"lounge": {"name": "lounge"}}, deleting=set()) == []


def test_export_leaves_out_empty_fields() -> None:
    fields = render_area({"name": "Kitchen", "icon": "mdi:stove"})
    assert export_area(fields) == {"name": "Kitchen", "icon": "mdi:stove"}
