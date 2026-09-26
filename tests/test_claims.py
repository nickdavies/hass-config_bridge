"""The claim functions other integrations call, with or without the bridge."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.config_bridge import claim_entities
from custom_components.config_bridge.lib.claims import claims_for


def fake_hass() -> Any:
    return SimpleNamespace(data={})


def test_claim_entities_records_items_in_the_yamls_shape() -> None:
    hass = fake_hass()
    claim_entities(
        hass, "lights", {"Switch.K": {"area_id": "kitchen"}, "light.a": None}
    )
    assert claims_for(hass.data, "entities") == {
        "lights": {"switch.k": {"area_id": "kitchen"}, "light.a": {}}
    }


def test_claim_entities_refuses_a_bad_item() -> None:
    with pytest.raises(ValueError, match="lights claimed entities"):
        claim_entities(fake_hass(), "lights", {"switch.k": {"room": "kitchen"}})
