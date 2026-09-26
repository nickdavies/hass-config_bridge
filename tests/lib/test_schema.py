"""The block schema's own rules, with a stand-in object type."""

from __future__ import annotations

import probatio
import pytest

from custom_components.config_bridge.lib.object_type import ObjectType
from custom_components.config_bridge.lib.schema import (
    bridge_schema,
    with_report_only,
)

THING = probatio.Schema({probatio.Required("size"): int})


def _no_kind():
    raise AssertionError("validating never loads a Kind")


BLOCK = bridge_schema({"thing": ObjectType("thing", THING, _no_kind)})


def test_report_only_defaults_to_false() -> None:
    assert BLOCK({"thing": {"size": 1}}) == {"thing": {"size": 1, "report_only": False}}


def test_report_only_never_reaches_the_object_types_schema() -> None:
    # THING doesn't list report_only, so it would refuse it as an extra key.
    assert with_report_only(THING)({"size": 1, "report_only": "yes"}) == {
        "size": 1,
        "report_only": True,
    }


def test_a_bad_report_only_points_at_it() -> None:
    with pytest.raises(probatio.Invalid) as err:
        BLOCK({"thing": {"size": 1, "report_only": "sometimes"}})
    assert err.value.path == ["thing", "report_only"]


def test_the_object_types_schema_applies() -> None:
    with pytest.raises(probatio.Invalid) as err:
        BLOCK({"thing": {"size": "big"}})
    assert err.value.path[:2] == ["thing", "size"]


def test_a_bare_block_is_empty() -> None:
    assert BLOCK(None) == {}


def test_object_types_are_optional_and_unknown_ones_refused() -> None:
    assert BLOCK({}) == {}
    with pytest.raises(probatio.Invalid):
        BLOCK({"other": {}})
