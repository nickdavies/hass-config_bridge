"""Config bridge: YAML as the source of truth for config HA now keeps elsewhere.

Home Assistant keeps moving settings out of `configuration.yaml` — into
config entries, into private `.storage` files, into registries — where they
stop being reviewable, reproducible and in git. This integration reads a
`config_bridge:` block and, on every boot, makes Home Assistant match it.

Each thing it manages is a *kind* (`http`, `mqtt`, `network`, `areas`), and
each kind is reconciled inside its own error boundary: if Home Assistant
changes something under one of them, that kind stops writing and reports —
a repair issue with the reason and the changes it would have made — and the
others carry on. Nothing about that is sticky; the next boot tries again.

**This module imports no Home Assistant at runtime.** Importing
`custom_components.config_bridge.model` runs this file first, so the
framework imports are either `TYPE_CHECKING`-only or done inside
`async_setup`. `tests/test_no_ha_imports.py` enforces it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import probatio as vol

from .const import DOMAIN
from .model.schema import BRIDGE_SCHEMA

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.typing import ConfigType

# Strict: an unknown kind or setting is an error, so `check_config` catches a
# typo before it ships. Only the YAML's shape is checked here — see
# `model/schema.py` for why Home Assistant's own rules wait until each kind
# runs.
CONFIG_SCHEMA = vol.Schema({DOMAIN: BRIDGE_SCHEMA}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Reconcile every configured kind. Never fails setup because of one."""
    from .bridge import async_setup_bridge  # noqa: PLC0415

    await async_setup_bridge(hass, config.get(DOMAIN) or {})
    return True
