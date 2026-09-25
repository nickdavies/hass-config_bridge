"""HTTP against Home Assistant's real config store.

The store is driven through its own methods into each state HA's HTTP setup
can leave it in at boot, then the bridge runs. None of this binds a server:
the bridge only ever touches the store, which is the point — HTTP can't be
applied on the boot the bridge runs in.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import patch

from homeassistant.components.http.config import (
    HTTP_STORAGE_SCHEMA,
    ActiveConfigType,
    HTTPConfigStore,
    async_get_and_load_store,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.config_bridge.object_types.http.model import (
    fingerprint,
    strip_meta,
)

from ..conftest import SetupBridge, ledger_storage, report

YAML = {
    "use_x_forwarded_for": True,
    "trusted_proxies": ["10.244.0.0/16", "10.96.0.0/12"],
}
UI_TRIAL = {"ip_ban_enabled": False}


def full(settings: dict[str, Any]) -> dict[str, Any]:
    """A config as the store holds it: HA's defaults filled in."""
    return dict(HTTP_STORAGE_SCHEMA(settings))


async def boot(
    hass: HomeAssistant,
    *,
    stable: dict[str, Any] | None = None,
    pending: dict[str, Any] | None = None,
    pending_error: str | None = None,
) -> HTTPConfigStore:
    """The store as HA's HTTP setup leaves it, stage 0, before the bridge runs."""
    store = await async_get_and_load_store(hass)
    if stable is not None:
        await store.async_set_pending(full(stable))
        await store.async_activate_config()
        await store.async_promote_pending()
    if pending is not None:
        await store.async_set_pending(full(pending))
        if pending_error is not None:
            store.pending["error"] = pending_error
    await store.async_activate_config()
    if store.active_config_type is ActiveConfigType.PENDING:
        store.async_schedule_revert_to_stable()
    return store


def pending_settings(store: HTTPConfigStore) -> dict[str, Any] | None:
    return strip_meta(store.pending) if store.pending is not None else None


async def test_stages_the_yaml_for_the_next_restart(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    store = await boot(hass)
    restart = async_mock_service(hass, "homeassistant", "restart")

    await setup_bridge({"http": YAML})

    assert pending_settings(store) == full(YAML)
    assert strip_meta(store.stable) == full({})
    assert restart == []
    assert report(hass, "http") is None


async def test_promotes_the_staged_config_it_boots_on(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    store = await boot(hass, pending=YAML)
    assert store.revert_deadline is not None

    await setup_bridge({"http": YAML})

    assert strip_meta(store.stable) == full(YAML)
    assert store.pending is None
    assert store.revert_deadline is None


async def test_in_sync_touches_nothing(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    store = await boot(hass, stable=YAML)

    await setup_bridge({"http": YAML})

    assert store.pending is None
    assert report(hass, "http") is None


async def test_discards_a_ui_trial_without_a_restart(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    store = await boot(hass, stable=YAML, pending=UI_TRIAL)
    restart = async_mock_service(hass, "homeassistant", "restart")

    await setup_bridge({"http": YAML})
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=6))
    await hass.async_block_till_done()

    assert store.pending is None
    assert strip_meta(store.stable) == full(YAML)
    assert restart == []


async def test_replaces_a_ui_trial_and_stops_its_revert(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    store = await boot(hass, pending=UI_TRIAL)
    restart = async_mock_service(hass, "homeassistant", "restart")

    await setup_bridge({"http": YAML})
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=6))
    await hass.async_block_till_done()

    assert pending_settings(store) == full(YAML)
    assert store.pending["error"] is None
    assert store.revert_deadline is None
    assert restart == []


async def test_never_restages_a_config_ha_could_not_apply(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    store = await boot(hass, pending=YAML, pending_error="apply_failed")

    await setup_bridge({"http": YAML})

    assert store.pending["error"] == "apply_failed"
    issue = report(hass, "http")
    assert issue is not None
    assert "could not apply" in issue.translation_placeholders["reason"]


async def test_restages_an_unpromoted_trial_once(
    hass: HomeAssistant, setup_bridge: SetupBridge, hass_storage: dict[str, Any]
) -> None:
    store = await boot(hass, pending=YAML, pending_error="not_promoted")

    await setup_bridge({"http": YAML})

    assert pending_settings(store) == full(YAML)
    assert store.pending["error"] is None
    assert hass_storage["config_bridge"]["data"]["http"]["restaged"] == fingerprint(
        full(YAML)
    )


async def test_does_not_restage_twice(
    hass: HomeAssistant, setup_bridge: SetupBridge, hass_storage: dict[str, Any]
) -> None:
    hass_storage["config_bridge"] = ledger_storage(
        {"http": {"restaged": fingerprint(full(YAML))}}
    )
    store = await boot(hass, pending=YAML, pending_error="not_promoted")

    await setup_bridge({"http": YAML})

    assert store.pending["error"] == "not_promoted"
    assert report(hass, "http") is not None


async def test_report_only_writes_nothing(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    store = await boot(hass)

    await setup_bridge({"http": {**YAML, "report_only": True}})

    assert store.pending is None
    issue = report(hass, "http")
    assert issue is not None
    assert "trusted_proxies" in issue.translation_placeholders["changes"]


async def test_unfamiliar_store_version_reports_instead_of_writing(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    store = await boot(hass)

    with patch("homeassistant.components.http.config.STORAGE_MINOR_VERSION", 3):
        await setup_bridge({"http": YAML})

    assert store.pending is None
    issue = report(hass, "http")
    assert issue is not None
    assert "version 2.3" in issue.translation_placeholders["reason"]


async def test_discards_a_leftover_failed_trial(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    store = await boot(
        hass, stable=YAML, pending=UI_TRIAL, pending_error="not_promoted"
    )

    await setup_bridge({"http": YAML})

    assert store.pending is None
    assert strip_meta(store.stable) == full(YAML)
