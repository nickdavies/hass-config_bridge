"""Network: the YAML's schema, and choosing the adapters discovery listens on.

The YAML may name an adapter directly (`eth0`) or by a network it has an
address in (`192.168.20.0/24`). The second exists because of how the pod is
wired: the multus attachments come up as `net1`, `net2`, … in the order the
annotation lists them, so a name encodes an ordering that lives in another
repo, while the subnet is the thing that actually identifies the VLAN.

Every selector has to match something. Home Assistant quietly falls back to
auto-detection when none of its configured names exist, so a stale name here
would not fail: it would silently change which networks get discovered.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Final

import probatio

from ...lib.validators import ensure_list, string

# --- the YAML ----------------------------------------------------------------


def is_network_selector(selector: str) -> bool:
    return "/" in selector


def _selector(value: Any) -> str:
    text = string(value)
    if is_network_selector(text):
        try:
            ipaddress.ip_network(text, strict=False)
        except ValueError as err:
            raise probatio.Invalid(str(err)) from err
    return text


SCHEMA: Final = probatio.Schema(
    {
        # An empty list is meaningful (auto-detection), so it is required
        # rather than defaulted: leaving it out is more likely a mistake.
        probatio.Required("adapters"): probatio.All(ensure_list, [_selector]),
    }
)

# --- selection ---------------------------------------------------------------


class SelectorError(ValueError):
    """A selector matches no adapter."""


@dataclass(frozen=True, slots=True)
class AdapterView:
    """An adapter as far as selection cares: its name and its addresses."""

    name: str
    addresses: tuple[str, ...]
    """Interface addresses in CIDR form, e.g. `192.168.20.9/24`."""


def resolve_adapters(
    selectors: Iterable[str], adapters: Sequence[AdapterView]
) -> tuple[str, ...]:
    """The adapter names the selectors pick, sorted and de-duplicated.

    No selectors means auto-detection, and resolves to no names — which is
    how Home Assistant itself stores "auto".
    """
    names: set[str] = set()
    unmatched: list[str] = []
    for selector in selectors:
        if is_network_selector(selector):
            network = ipaddress.ip_network(selector, strict=False)
            hits = [
                adapter.name
                for adapter in adapters
                if any(
                    ipaddress.ip_interface(address).ip in network
                    for address in adapter.addresses
                )
            ]
        else:
            hits = [adapter.name for adapter in adapters if adapter.name == selector]
        if not hits:
            unmatched.append(selector)
        names.update(hits)
    if unmatched:
        available = ", ".join(
            f"{name} ({', '.join(networks) or 'no addresses'})"
            for name, networks in describe_adapters(adapters).items()
        )
        raise SelectorError(
            f"No adapter matches {', '.join(unmatched)}. Available: {available}."
        )
    return tuple(sorted(names))


def describe_adapters(adapters: Iterable[AdapterView]) -> dict[str, list[str]]:
    """Adapter name → the networks it is on, for errors and `export`."""
    return {
        adapter.name: sorted(
            {
                str(ipaddress.ip_interface(address).network)
                for address in adapter.addresses
            }
        )
        for adapter in sorted(adapters, key=lambda adapter: adapter.name)
    }
