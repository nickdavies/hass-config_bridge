"""Everything but the Home Assistant side must import without Home Assistant.

Not a style preference. It is what lets every other unit test run against the
real code with real type hints and no framework mocking.

The usual way this breaks is innocent: a `homeassistant.const` import added
to the package root for one constant, and every unit test in the repo
silently starts needing Home Assistant.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "custom_components" / "config_bridge"

HA_SIDE = frozenset({"lib.runner", "lib.ledger"})
"""The engine's Home Assistant side. Each object type's `kind` is too."""


def _modules() -> list[str]:
    """Every module of the integration that must not need Home Assistant."""
    modules = []
    for path in sorted(PACKAGE.rglob("*.py")):
        parts = path.relative_to(PACKAGE).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if ".".join(parts) in HA_SIDE:
            continue
        if len(parts) == 3 and parts[0] == "object_types" and parts[2] == "kind":
            continue
        modules.append(".".join(("custom_components", "config_bridge", *parts)))
    return modules


def _import_in_subprocess(module: str) -> subprocess.CompletedProcess[str]:
    """Import in a fresh interpreter.

    A subprocess rather than an in-process check because by the time this test
    runs, another test in the same session may already have imported Home
    Assistant, and `sys.modules` would then show it regardless of who pulled
    it in.
    """
    code = (
        "import sys\n"
        f"import {module}\n"
        "ha = sorted(m for m in sys.modules if m == 'homeassistant'"
        " or m.startswith('homeassistant.'))\n"
        "print(':'.join(ha))\n"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )


def test_the_module_list_covers_both_halves() -> None:
    modules = _modules()
    assert "custom_components.config_bridge" in modules
    assert "custom_components.config_bridge.lib.schema" in modules
    assert "custom_components.config_bridge.object_types.areas.model" in modules
    assert "custom_components.config_bridge.lib.runner" not in modules
    assert "custom_components.config_bridge.object_types.areas.kind" not in modules


def test_imports_without_home_assistant() -> None:
    for module in _modules():
        result = _import_in_subprocess(module)
        assert result.returncode == 0, f"importing {module} failed:\n{result.stderr}"
        pulled_in = [name for name in result.stdout.strip().split(":") if name]
        assert not pulled_in, (
            f"importing {module} pulled in Home Assistant: {pulled_in}. "
            "Move the import into a function or behind TYPE_CHECKING: the unit "
            "tests run without HA installed."
        )
