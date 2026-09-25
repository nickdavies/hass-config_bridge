"""The model must stay importable without Home Assistant.

Not a style preference. It is what lets every other unit test run against the
real code with real type hints and no framework mocking — and it is the hedge
the README describes: the decisions live apart from how they are read and
written, so they survive a change in how the bridge talks to Home Assistant.

The usual way this breaks is innocent: a `homeassistant.const` import added
to the package root for one constant, and every unit test in the repo
silently starts needing Home Assistant.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Imported for their side effect on sys.modules: each one runs the package
# __init__ chain above it, which is where an HA import would sneak in.
MUST_IMPORT_CLEAN = (
    "custom_components.config_bridge",
    "custom_components.config_bridge.const",
    "custom_components.config_bridge.model",
    "custom_components.config_bridge.model.areas",
    "custom_components.config_bridge.model.collection",
    "custom_components.config_bridge.model.diff",
    "custom_components.config_bridge.model.http",
    "custom_components.config_bridge.model.mqtt",
    "custom_components.config_bridge.model.network",
    "custom_components.config_bridge.model.plan",
    "custom_components.config_bridge.model.schema",
)


def _import_in_subprocess(module: str) -> subprocess.CompletedProcess[str]:
    """Import in a fresh interpreter.

    A subprocess rather than an in-process check because by the time this test
    runs, another test in the same session may already have imported Home
    Assistant — `sys.modules` would then show it regardless of who pulled it in.
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


def test_model_imports_without_home_assistant() -> None:
    for module in MUST_IMPORT_CLEAN:
        result = _import_in_subprocess(module)
        assert result.returncode == 0, f"importing {module} failed:\n{result.stderr}"
        pulled_in = [name for name in result.stdout.strip().split(":") if name]
        assert not pulled_in, (
            f"importing {module} pulled in Home Assistant: {pulled_in}. "
            "Move the import into a function or behind TYPE_CHECKING — the unit "
            "tests run without HA installed."
        )
