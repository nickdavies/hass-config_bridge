"""Config bridge: Home Assistant settings kept in YAML and applied at every boot.

Home Assistant keeps some settings only in config entries, `.storage` files
and registries, where they are set from the UI. This integration reads a
`config_bridge:` block and, on every boot, makes Home Assistant match it.

It has two halves:

- `object_types/`: one package per thing the bridge manages (`http`, `mqtt`,
  `network`, `areas`), each with its schema and decisions in `model.py` and
  the code that reads and writes Home Assistant in `kind.py`.
- `lib/`: what they share: the runner and its error boundaries, plans,
  diffs, collection planning, shared validators and the ledger.

This module wires the two together: `CONFIG_SCHEMA` from the object types'
schemas, and a setup that hands the configured object types to the runner.

**This module imports no Home Assistant at runtime.** Importing any module
of the integration runs this file first, so the framework imports are
either `TYPE_CHECKING`-only or done inside `async_setup`.
`tests/test_no_ha_imports.py` enforces it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import probatio

from .const import DOMAIN
from .lib.schema import bridge_schema
from .object_types import OBJECT_TYPES

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.typing import ConfigType

# Strict: an unknown object type or setting is an error, so `check_config`
# catches a typo before it ships. `lib/schema.py` says what is checked here
# and what is left to each object type.
CONFIG_SCHEMA = probatio.Schema(
    {DOMAIN: bridge_schema(OBJECT_TYPES)}, extra=probatio.ALLOW_EXTRA
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Reconcile every configured object type. Never fails setup because of one."""
    from .lib.runner import async_setup_bridge  # noqa: PLC0415

    await async_setup_bridge(hass, config.get(DOMAIN) or {}, OBJECT_TYPES)
    return True
