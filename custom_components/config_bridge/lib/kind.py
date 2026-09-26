"""The interface between the runner and one object type's Home Assistant side."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .ledger import KindState
    from .plan import Plan


class KindError(Exception):
    """This object type can't be reconciled. The message is the report's reason.

    Raised for anything a Kind recognises: a store version it wasn't written
    against, a live object with keys it doesn't know, a reference to
    something that doesn't exist. Anything else that escapes is caught by the
    runner too; this lets the report say why in words.
    """


class RunAt(Enum):
    SETUP = "setup"
    """As soon as the bridge loads, during bootstrap."""
    STARTED = "started"
    """Once Home Assistant has started and every integration's entities exist."""


class Kind(ABC):
    """Reads and writes Home Assistant for one object type.

    The runner calls `async_plan`, then, unless the plan is in sync or
    blocked or the object type is report-only, `async_apply` and
    `async_verify`. Each call reads Home Assistant afresh; nothing is cached
    between them, so verify checks what is actually there.
    """

    run_at: ClassVar[RunAt] = RunAt.SETUP

    hass: HomeAssistant
    settings: Mapping[str, Any]
    """The object type's validated YAML, without `report_only`."""
    state: KindState
    """The object type's own slice of the ledger."""

    def __init__(
        self, hass: HomeAssistant, settings: Mapping[str, Any], state: KindState
    ) -> None:
        self.hass = hass
        self.settings = settings
        self.state = state

    @abstractmethod
    async def async_plan(self) -> Plan:
        """Read Home Assistant and decide. Must not write anything."""

    @abstractmethod
    async def async_apply(self, plan: Plan) -> None:
        """Make the writes the plan describes."""

    @abstractmethod
    async def async_verify(self, plan: Plan) -> None:
        """Re-read and raise `KindError` if Home Assistant doesn't match."""

    async def async_remember(self, plan: Plan) -> None:
        """Record state once the object type is known to match the YAML.

        Called after a successful apply *and* when already in sync: an
        `owned` area that already matched on the first run is still owned
        from then on. Not called when reporting.
        """

    @classmethod
    @abstractmethod
    async def async_export(cls, hass: HomeAssistant) -> Any:
        """What Home Assistant has, in the shape of this object type's YAML."""
