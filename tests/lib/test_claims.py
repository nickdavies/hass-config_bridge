"""Claims: recording an integration's items, and merging them with the YAML's."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.config_bridge.lib.claims import (
    CLAIMS,
    YAML_OWNER,
    claimed_by,
    claims_for,
    merge_claims,
    record_claim,
)
from custom_components.config_bridge.lib.validators import keyed_by_slug, slug

SCHEMA = keyed_by_slug(slug)


def test_a_claim_is_validated_and_recorded_per_object_type_and_owner() -> None:
    data: dict[str, Any] = {}
    record_claim(data, "things", "lights", {"a": "kitchen"}, SCHEMA)
    record_claim(data, "things", "plants", {"b": "lounge"}, SCHEMA)
    record_claim(data, "others", "lights", {"c": "hall"}, SCHEMA)
    assert data[CLAIMS] == {
        "things": {"lights": {"a": "kitchen"}, "plants": {"b": "lounge"}},
        "others": {"lights": {"c": "hall"}},
    }
    assert claims_for(data, "things")["plants"] == {"b": "lounge"}
    assert claims_for(data, "nothing") == {}


def test_claiming_again_replaces_the_owners_claim() -> None:
    data: dict[str, Any] = {}
    record_claim(data, "things", "lights", {"a": "kitchen"}, SCHEMA)
    record_claim(data, "things", "lights", {"b": "kitchen"}, SCHEMA)
    assert claims_for(data, "things") == {"lights": {"b": "kitchen"}}


def test_a_bad_claim_names_its_owner_and_records_nothing() -> None:
    data: dict[str, Any] = {}
    with pytest.raises(ValueError, match="lights claimed things"):
        record_claim(data, "things", "lights", {"a": "Not A Slug"}, SCHEMA)
    assert data == {}


def test_the_yamls_name_is_not_an_owner() -> None:
    with pytest.raises(ValueError, match="the YAML"):
        record_claim({}, "things", YAML_OWNER, {}, SCHEMA)


def test_merge_keeps_each_owner_and_renders() -> None:
    merged, conflicts = merge_claims({"a": 1}, {"plants": {"b": 2}}, lambda n: n * 10)
    assert conflicts == []
    assert merged == {"a": (YAML_OWNER, 10), "b": ("plants", 20)}


def test_a_key_listed_twice_is_a_conflict_not_a_merge() -> None:
    merged, conflicts = merge_claims(
        {"a": 1},
        {"lights": {"a": 1}, "plants": {"a": 1, "b": 2}},
        lambda n: n,
    )
    assert conflicts == ["a is listed by the YAML and lights and plants"]
    assert merged == {"b": ("plants", 2)}


def test_claimed_by() -> None:
    assert claimed_by(YAML_OWNER) == ""
    assert claimed_by("plants") == " (claimed by plants)"
