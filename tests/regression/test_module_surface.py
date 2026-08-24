"""Regression: the public module surface must not shrink silently.

A concrete, runnable regression guard from Phase 0 onward. It walks the ``hip``
package and compares the set of importable modules against a committed golden
file (``golden_module_surface.txt``). If a module is removed or renamed without
updating the golden file, this fails — catching accidental deletions and
surfacing intentional API changes in review rather than in production.

Update the golden file deliberately (never blindly) when a module is added or
removed on purpose:

    uv run python -m tests.regression.test_module_surface --update
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.regression

GOLDEN = Path(__file__).with_name("golden_module_surface.txt")


def _current_surface() -> list[str]:
    """Every importable module under the ``hip`` package, sorted."""
    import hip

    names = {"hip"}
    for info in pkgutil.walk_packages(hip.__path__, prefix="hip."):
        names.add(info.name)
    return sorted(names)


def _read_golden() -> list[str]:
    return [
        line.strip()
        for line in GOLDEN.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def test_module_surface_matches_golden() -> None:
    """The set of importable hip modules matches the reviewed golden file."""
    current = _current_surface()
    golden = _read_golden()

    removed = sorted(set(golden) - set(current))
    added = sorted(set(current) - set(golden))

    assert not removed, (
        f"Modules disappeared from the public surface: {removed}. "
        "If intentional, update golden_module_surface.txt in the same change."
    )
    assert not added, (
        f"New modules not yet in the golden surface: {added}. "
        "If intentional, run this file with --update and commit the golden file."
    )


def _update_golden() -> None:
    header = (
        "# Golden module surface for the `hip` package (regression guard).\n"
        "# Update deliberately when modules are intentionally added/removed.\n"
        "# Regenerate: uv run python -m tests.regression.test_module_surface --update\n"
    )
    GOLDEN.write_text(header + "\n".join(_current_surface()) + "\n", encoding="utf-8")


if __name__ == "__main__":
    if "--update" in sys.argv:
        # Ensure src/ is importable when run as a script.
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
        importlib.invalidate_caches()
        _update_golden()
        print(f"Wrote {GOLDEN}")
    else:
        raise SystemExit("Run via pytest, or pass --update to regenerate the golden file.")
