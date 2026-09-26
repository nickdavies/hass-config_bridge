"""HTTP: the YAML's schema, and what to do with Home Assistant's HTTP config store.

The HTTP server binds in bootstrap stage 0, before any custom integration
loads, so a change never applies on the boot the bridge runs in. Home
Assistant's own way of changing it is a two-slot store: `stable`, the last
config known to work, and `pending`, a trial for the next boot, plus a
five-minute timer that reverts an unpromoted trial and restarts. The bridge
works with that rather than around it: it stages the YAML as `pending` for
the next restart, and on the boot that runs it, promotes it before the timer
fires. It never restarts Home Assistant itself.

Everything here is a pure function of what the store holds, so every branch,
including the ones that only happen when something has gone wrong, is unit
tested.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

import probatio

from ...lib.validators import ensure_list, ip_network, port, string

# --- the YAML ----------------------------------------------------------------


def _forwarded_for_needs_proxies(conf: dict[str, Any]) -> dict[str, Any]:
    """HA's settings page refuses this pair, and so would the store."""
    if conf.get("use_x_forwarded_for") and not conf.get("trusted_proxies"):
        raise probatio.Invalid(
            "use_x_forwarded_for needs at least one trusted proxy",
            path=["trusted_proxies"],
        )
    return conf


SCHEMA: Final = probatio.All(
    probatio.Schema(
        {
            probatio.Optional("server_host"): probatio.All(
                ensure_list, probatio.Length(min=1), [string]
            ),
            probatio.Optional("server_port"): port,
            probatio.Optional("ssl_certificate"): string,
            probatio.Optional("ssl_peer_certificate"): string,
            probatio.Optional("ssl_key"): string,
            probatio.Optional("cors_allowed_origins"): probatio.All(
                ensure_list, [string]
            ),
            probatio.Optional("use_x_forwarded_for"): probatio.Boolean(),
            probatio.Optional("trusted_proxies"): probatio.All(
                ensure_list, [ip_network]
            ),
            probatio.Optional("login_attempts_threshold"): probatio.Any(
                probatio.All(probatio.Coerce(int), probatio.Range(min=0)), -1
            ),
            probatio.Optional("ip_ban_enabled"): probatio.Boolean(),
            probatio.Optional("ssl_profile"): probatio.In(["intermediate", "modern"]),
            probatio.Optional("use_x_frame_options"): probatio.Boolean(),
        }
    ),
    _forwarded_for_needs_proxies,
)
"""The settings of Home Assistant's `http:` key, in the same shape (`base_url`
excepted). The Kind applies Home Assistant's own schema on top, which fills
in its defaults."""

# --- the store ---------------------------------------------------------------

# The store's own vocabulary, at storage version 2.2. The Kind checks Home
# Assistant uses these exact values before trusting any decision made here.
ACTIVE_STABLE: Final = "stable"
ACTIVE_PENDING: Final = "pending"
ERROR_APPLY_FAILED: Final = "apply_failed"
ERROR_NOT_PROMOTED: Final = "not_promoted"
META_KEYS: Final = ("created_at", "error", "error_message")


class HttpAction(StrEnum):
    NOTHING = "nothing"
    PROMOTE = "promote"
    """HA is running on a trial that is the YAML's config: make it stable."""
    STAGE = "stage"
    """Queue the YAML's config as the trial for the next boot."""
    RESTAGE = "restage"
    """As STAGE, for a config whose previous trial was reverted unpromoted."""
    DISCARD_PENDING = "discard_pending"
    """A trial that isn't the YAML's, while stable already is: drop it."""
    REPLACE_TRIAL = "replace_trial"
    """HA is running on someone else's trial and stable isn't the YAML's
    either: stop HA's revert timer and queue the YAML's config instead."""
    REFUSE = "refuse"


@dataclass(frozen=True, slots=True)
class HttpDecision:
    action: HttpAction
    reason: str


def strip_meta(config: Mapping[str, Any]) -> dict[str, Any]:
    """The settings of a stored slot, without the store's bookkeeping."""
    return {key: value for key, value in config.items() if key not in META_KEYS}


def fingerprint(config: Mapping[str, Any]) -> str:
    """Stable identity for a config, to remember "already re-staged this one"."""
    encoded = json.dumps(config, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def decide_http(
    *,
    desired: Mapping[str, Any],
    stable: Mapping[str, Any],
    pending: Mapping[str, Any] | None,
    pending_error: str | None,
    pending_error_message: str | None,
    active: str,
    restaged: bool,
) -> HttpDecision:
    """What to do, given the YAML's config and what the store holds.

    `stable` and `pending` are stripped of metadata. `active` is the slot the
    running server was started with. `restaged` says the bridge has already
    re-staged exactly this config once after a trial of it was reverted.
    """
    if active == ACTIVE_PENDING:
        # HA only starts a pending config that hasn't failed, so there is no
        # error to look at on this path.
        if pending == desired:
            return HttpDecision(
                HttpAction.PROMOTE, "Running on the staged YAML config."
            )
        if stable == desired:
            return HttpDecision(
                HttpAction.DISCARD_PENDING,
                "Running on a trial config that isn't the YAML's; the stable "
                "config already matches the YAML, so the trial is discarded.",
            )
        return HttpDecision(
            HttpAction.REPLACE_TRIAL,
            "Running on a trial config that isn't the YAML's.",
        )

    if active != ACTIVE_STABLE:
        return HttpDecision(
            HttpAction.REFUSE,
            f"HA reports the running HTTP config came from {active!r}, which "
            "the bridge doesn't know how to handle.",
        )

    if stable == desired:
        if pending is None:
            return HttpDecision(HttpAction.NOTHING, "In sync.")
        return HttpDecision(
            HttpAction.DISCARD_PENDING,
            "A failed trial config is left over; the stable config already "
            "matches the YAML.",
        )

    if pending != desired:
        return HttpDecision(
            HttpAction.STAGE, "The stable config differs from the YAML."
        )

    # The YAML's config is already pending, but HA didn't start it.
    if pending_error == ERROR_APPLY_FAILED:
        detail = f": {pending_error_message}" if pending_error_message else "."
        return HttpDecision(
            HttpAction.REFUSE,
            f"Home Assistant could not apply this HTTP config{detail} "
            "It will not be staged again until the YAML changes.",
        )
    if pending_error == ERROR_NOT_PROMOTED:
        if restaged:
            return HttpDecision(
                HttpAction.REFUSE,
                "This HTTP config has been staged twice and HA reverted it "
                "both times before the bridge could promote it.",
            )
        return HttpDecision(
            HttpAction.RESTAGE,
            "HA reverted the last trial of this config before it was promoted.",
        )
    return HttpDecision(
        HttpAction.REFUSE,
        f"The YAML's config is pending but HA didn't start it "
        f"(error: {pending_error!r}); the bridge doesn't know why.",
    )


def export_http(
    stable: Mapping[str, Any], defaults: Mapping[str, Any]
) -> dict[str, Any]:
    """The stable config as bridge YAML: only what differs from HA's defaults."""
    return {
        key: value
        for key, value in sorted(stable.items())
        if key not in defaults or defaults[key] != value
    }
