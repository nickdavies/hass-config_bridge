"""HTTP's model: the YAML's schema, and every branch of the decision, since most
of them only happen when something has already gone wrong."""

from __future__ import annotations

from typing import Any

import probatio as vol
import pytest

from custom_components.config_bridge.object_types.http.model import (
    ERROR_APPLY_FAILED,
    ERROR_NOT_PROMOTED,
    SCHEMA,
    HttpAction,
    decide_http,
    export_http,
    fingerprint,
    strip_meta,
)

YAML = {"use_x_forwarded_for": True, "trusted_proxies": ["10.244.0.0/16"]}
DEFAULTS = {"server_port": 8123}
UI_TRIAL = {"use_x_forwarded_for": False}


def decide(
    *,
    stable: dict[str, Any],
    pending: dict[str, Any] | None = None,
    error: str | None = None,
    active: str = "stable",
    restaged: bool = False,
):
    return decide_http(
        desired=YAML,
        stable=stable,
        pending=pending,
        pending_error=error,
        pending_error_message="port in use" if error else None,
        active=active,
        restaged=restaged,
    ).action


def test_in_sync() -> None:
    assert decide(stable=YAML) is HttpAction.NOTHING


def test_stable_differs_stages_for_next_restart() -> None:
    assert decide(stable=DEFAULTS) is HttpAction.STAGE


def test_staged_config_running_is_promoted() -> None:
    assert decide(stable=DEFAULTS, pending=YAML, active="pending") is HttpAction.PROMOTE


def test_ui_trial_running_while_stable_matches_is_discarded() -> None:
    # Discarding is enough: HA's revert timer then finds nothing to revert, so
    # the next boot is back on stable with no restart in between.
    assert (
        decide(stable=YAML, pending=UI_TRIAL, active="pending")
        is HttpAction.DISCARD_PENDING
    )


def test_ui_trial_running_while_stable_differs_is_replaced() -> None:
    assert (
        decide(stable=DEFAULTS, pending=UI_TRIAL, active="pending")
        is HttpAction.REPLACE_TRIAL
    )


def test_leftover_failed_trial_is_discarded_when_stable_matches() -> None:
    assert (
        decide(stable=YAML, pending=UI_TRIAL, error=ERROR_NOT_PROMOTED)
        is HttpAction.DISCARD_PENDING
    )


def test_different_failed_trial_is_overwritten_by_staging() -> None:
    assert (
        decide(stable=DEFAULTS, pending=UI_TRIAL, error=ERROR_APPLY_FAILED)
        is HttpAction.STAGE
    )


def test_config_ha_could_not_bind_is_never_restaged() -> None:
    decision = decide_http(
        desired=YAML,
        stable=DEFAULTS,
        pending=YAML,
        pending_error=ERROR_APPLY_FAILED,
        pending_error_message="port 80 in use",
        active="stable",
        restaged=False,
    )
    assert decision.action is HttpAction.REFUSE
    assert "port 80 in use" in decision.reason


def test_unpromoted_trial_is_restaged_once() -> None:
    assert (
        decide(stable=DEFAULTS, pending=YAML, error=ERROR_NOT_PROMOTED)
        is HttpAction.RESTAGE
    )


def test_unpromoted_trial_is_not_restaged_twice() -> None:
    assert (
        decide(stable=DEFAULTS, pending=YAML, error=ERROR_NOT_PROMOTED, restaged=True)
        is HttpAction.REFUSE
    )


@pytest.mark.parametrize("error", [None, "something_new"])
def test_unexplained_pending_state_is_refused(error: str | None) -> None:
    # Pending, error-free and not running only happens in recovery mode, where
    # the bridge doesn't load; an unknown error code is a store we don't know.
    assert decide(stable=DEFAULTS, pending=YAML, error=error) is HttpAction.REFUSE


@pytest.mark.parametrize("active", ["default", "default_legacy_port", "unheard_of"])
def test_unfamiliar_running_slot_is_refused(active: str) -> None:
    assert decide(stable=DEFAULTS, active=active) is HttpAction.REFUSE


def test_strip_meta_keeps_only_settings() -> None:
    stored = {**YAML, "created_at": "2026-09-01", "error": None, "error_message": None}
    assert strip_meta(stored) == YAML


def test_fingerprint_ignores_key_order() -> None:
    assert fingerprint({"a": 1, "b": [2]}) == fingerprint({"b": [2], "a": 1})
    assert fingerprint({"a": 1}) != fingerprint({"a": 2})


def test_export_leaves_out_defaults() -> None:
    stable = {**DEFAULTS, **YAML, "ip_ban_enabled": True}
    defaults = {**DEFAULTS, "ip_ban_enabled": True}
    assert export_http(stable, defaults) == YAML


# --- the YAML ----------------------------------------------------------------


def test_trusted_proxies_must_be_networks_with_no_host_bits() -> None:
    # Strict like Home Assistant's own schema, so CI refuses what HA would.
    with pytest.raises(vol.Invalid):
        SCHEMA({"trusted_proxies": ["10.244.0.1/16"]})
    with pytest.raises(vol.Invalid):
        SCHEMA({"trusted_proxies": ["not-a-network"]})


def test_forwarded_for_needs_a_trusted_proxy() -> None:
    with pytest.raises(vol.Invalid, match="trusted proxy"):
        SCHEMA({"use_x_forwarded_for": True})


def test_login_threshold_accepts_the_disabled_sentinel() -> None:
    assert SCHEMA({"login_attempts_threshold": -1})["login_attempts_threshold"] == -1
    with pytest.raises(vol.Invalid):
        SCHEMA({"login_attempts_threshold": -2})
