"""Integration fixtures — a real Home Assistant, via
pytest-homeassistant-custom-component, pinned to the version homelab deploys.

The unit tests cover the decisions. These cover what only a running Home
Assistant can show: that the Kinds read and write the real stores and
registries the way the decisions assume, and that one object type failing
leaves the others alone.
"""

from __future__ import annotations

import pathlib
import sys
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.loader import DATA_CUSTOM_COMPONENTS
from homeassistant.setup import async_setup_component

DOMAIN = "config_bridge"

REPO_ROOT = pathlib.Path(__file__).parent.parent

SetupBridge = Callable[[dict[str, Any]], Awaitable[None]]


def _ensure_custom_components_path() -> None:
    """Put this project's custom_components on the namespace path.

    pytest-homeassistant-custom-component points the `custom_components`
    namespace package at its own testing_config directory, so without this the
    component under test is invisible.
    """
    import custom_components

    path = str(REPO_ROOT / "custom_components")
    if path in custom_components.__path__:
        return
    if isinstance(custom_components.__path__, list):
        custom_components.__path__.insert(0, path)
    else:
        # A namespace package, whose path follows sys.path.
        sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def setup_bridge(hass: HomeAssistant) -> SetupBridge:
    """Set the bridge up with a `config_bridge:` block, as a boot would."""

    async def setup(conf: dict[str, Any]) -> None:
        hass.data.pop(DATA_CUSTOM_COMPONENTS, None)
        _ensure_custom_components_path()
        assert await async_setup_component(hass, DOMAIN, {DOMAIN: conf}), "setup failed"
        await hass.async_block_till_done()

    return setup


def report(hass: HomeAssistant, object_type: str) -> ir.IssueEntry | None:
    """The repair issue an object type raised when it didn't apply, if it did."""
    return ir.async_get(hass).async_get_issue(DOMAIN, f"report_{object_type}")


def ledger_storage(data: dict[str, Any]) -> dict[str, Any]:
    """`.storage/config_bridge` as the bridge writes it, for `hass_storage`.

    `data` maps each object type's name to its own state.
    """
    return {"version": 1, "minor_version": 1, "key": DOMAIN, "data": data}
