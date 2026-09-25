"""HTTP: Home Assistant's private HTTP config store, from the YAML.

See `model/http.py` for how the stable/pending store and its revert timer
are handled. This adapter reads the store, hands it to `decide_http`, and
carries out the decision.

Coupled to `homeassistant.components.http.config`, which is internal and new
(2026.7), and likely to change again when Home Assistant stops importing the
`http:` YAML key in 2027.2. So it checks the store's version and vocabulary
before trusting it, and reports instead of writing when they've moved.
"""

from __future__ import annotations

from types import ModuleType
from typing import Any, Final, cast

import voluptuous as vol
from homeassistant.core import HomeAssistant

from ..model import http as model
from ..model.diff import diff_fields
from ..model.http import HttpAction, HttpDecision
from ..model.plan import Plan, Step
from .base import Kind, KindError

STORE_VERSION: Final = (2, 2)
"""The `.storage/http` version this adapter was written against."""

_NEXT_RESTART: Final = "Takes effect the next time Home Assistant restarts."


def _store_api() -> ModuleType:
    """Home Assistant's HTTP config module, if it is still the one we know."""
    from homeassistant.components.http import config as http_config  # noqa: PLC0415

    version = (http_config.STORAGE_VERSION, http_config.STORAGE_MINOR_VERSION)
    if version != STORE_VERSION:
        raise KindError(
            f"Home Assistant's HTTP config store is at version "
            f"{version[0]}.{version[1]}; this bridge was written against "
            f"{STORE_VERSION[0]}.{STORE_VERSION[1]}."
        )
    # The decision logic is written in terms of these values. If Home
    # Assistant renames one, the logic is wrong rather than just stale.
    expected = {
        "ERROR_APPLY_FAILED": model.ERROR_APPLY_FAILED,
        "ERROR_NOT_PROMOTED": model.ERROR_NOT_PROMOTED,
        "HTTP_CONFIG_CREATED_AT": "created_at",
        "HTTP_CONFIG_ERROR": "error",
        "HTTP_CONFIG_ERROR_MESSAGE": "error_message",
    }
    for attribute, value in expected.items():
        if getattr(http_config, attribute, None) != value:
            raise KindError(
                f"Home Assistant's HTTP config store no longer defines "
                f"{attribute} as {value!r}."
            )
    active_types = {member.value for member in http_config.ActiveConfigType}
    if not {model.ACTIVE_STABLE, model.ACTIVE_PENDING} <= active_types:
        raise KindError(
            f"Home Assistant's HTTP config store reports unfamiliar slots: "
            f"{sorted(active_types)}."
        )
    return http_config


class HttpKind(Kind):
    name = "http"

    async def async_plan(self) -> Plan:
        http_config = _store_api()
        try:
            # Home Assistant's own schema, so its defaults fill in anything
            # the YAML leaves out: an omitted setting means HA's default.
            desired = dict(http_config.HTTP_STORAGE_SCHEMA(self.settings))
        except vol.Invalid as err:
            raise KindError(f"Home Assistant rejects this HTTP config: {err}") from err

        store = await http_config.async_get_and_load_store(self.hass)
        stable = model.strip_meta(store.stable)
        raw_pending = store.pending
        pending = model.strip_meta(raw_pending) if raw_pending is not None else None
        decision = model.decide_http(
            desired=desired,
            stable=stable,
            pending=pending,
            pending_error=raw_pending.get("error") if raw_pending else None,
            pending_error_message=(
                raw_pending.get("error_message") if raw_pending else None
            ),
            active=str(store.active_config_type),
            restaged=self.ledger.http_restaged == model.fingerprint(desired),
        )
        return _plan_for(decision, desired, stable, pending)

    async def async_apply(self, plan: Plan) -> None:
        action, desired = plan.payload
        store = await _store_api().async_get_and_load_store(self.hass)
        if action is HttpAction.PROMOTE:
            await store.async_promote_pending()
            await self.ledger.async_set_http_restaged(None)
        elif action in (HttpAction.STAGE, HttpAction.RESTAGE):
            # A copy: the store stamps its metadata onto the dict it is given.
            await store.async_set_pending(dict(desired))
            await self.ledger.async_set_http_restaged(
                model.fingerprint(desired) if action is HttpAction.RESTAGE else None
            )
        elif action is HttpAction.REPLACE_TRIAL:
            # Without this, HA's timer would mark the YAML's config as the
            # failed trial in five minutes and restart to revert it.
            store.async_cancel_revert()
            await store.async_set_pending(dict(desired))
            await self.ledger.async_set_http_restaged(None)
        elif action is HttpAction.DISCARD_PENDING:
            # If a trial is running, its timer now finds nothing to revert and
            # does nothing — no restart.
            await store.async_set_pending(None)
        else:  # pragma: no cover - the runner never applies other actions
            raise KindError(f"Nothing to apply for {action}.")

    async def async_verify(self, plan: Plan) -> None:
        action, desired = plan.payload
        store = await _store_api().async_get_and_load_store(self.hass)
        pending = store.pending
        if action is HttpAction.PROMOTE:
            ok = model.strip_meta(store.stable) == desired and pending is None
        elif action is HttpAction.DISCARD_PENDING:
            ok = pending is None
        else:
            ok = (
                pending is not None
                and model.strip_meta(pending) == desired
                and pending.get("error") is None
            )
            if action is HttpAction.REPLACE_TRIAL:
                ok = ok and store.revert_deadline is None
        if not ok:
            raise KindError(
                f"After {action}, Home Assistant's HTTP store doesn't hold the "
                "YAML's config."
            )

    @classmethod
    async def async_export(cls, hass: HomeAssistant) -> Any:
        http_config = _store_api()
        store = await http_config.async_get_and_load_store(hass)
        defaults = http_config.HTTP_STORAGE_SCHEMA({})
        return model.export_http(model.strip_meta(store.stable), defaults)


def _plan_for(
    decision: HttpDecision,
    desired: dict[str, Any],
    stable: dict[str, Any],
    pending: dict[str, Any] | None,
) -> Plan:
    action = decision.action
    payload = (action, desired)
    if action is HttpAction.NOTHING:
        return Plan()
    if action is HttpAction.PROMOTE:
        return Plan(
            steps=(
                Step(
                    "Promote the staged HTTP config Home Assistant is running on",
                    diff_fields(desired, stable),
                ),
            ),
            payload=payload,
        )
    if action is HttpAction.DISCARD_PENDING:
        return Plan(
            steps=(
                Step(
                    "Discard a pending HTTP config that isn't the YAML's",
                    diff_fields(desired, cast(dict[str, Any], pending or {})),
                ),
            ),
            note=decision.reason,
            payload=payload,
        )
    stage = Step(
        "Stage the YAML's HTTP config for the next restart",
        diff_fields(desired, stable),
    )
    if action is HttpAction.REFUSE:
        return Plan(steps=(stage,), blocked=decision.reason, payload=payload)
    note = _NEXT_RESTART
    if action is HttpAction.REPLACE_TRIAL:
        note = f"{decision.reason} {_NEXT_RESTART}"
    return Plan(steps=(stage,), note=note, payload=payload)
