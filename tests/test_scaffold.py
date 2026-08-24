"""Phase 0 smoke tests — the scaffold imports and the package tree is intact.

These assert structure only (there is no business logic yet). They exist so CI
has something green to run and so a broken import surfaces immediately. Real
behavioural tests arrive with each layer, per docs/TEST_STRATEGY.md.
"""

from __future__ import annotations

import importlib

import pytest

# Every module in the scaffold. If one fails to import, the scaffold is broken.
SCAFFOLD_MODULES = [
    "hip",
    "hip.platform",
    "hip.platform.paths",
    "hip.gateway",
    "hip.gateway.api",
    "hip.gateway.api.fhir",
    "hip.gateway.api.admin",
    "hip.gateway.auth",
    "hip.gateway.ratelimit",
    "hip.messaging",
    "hip.messaging.hl7",
    "hip.messaging.hl7.listener",
    "hip.messaging.hl7.parser",
    "hip.messaging.hl7.router",
    "hip.messaging.canonical",
    "hip.messaging.canonical.mapper",
    "hip.messaging.validator",
    "hip.persistence",
    "hip.persistence.phi_repo",
    "hip.persistence.audit_log",
    "hip.persistence.deid_repo",
    "hip.security",
    "hip.security.keymanager",
    "hip.security.secrets",
    "hip.security.objectstore",
    "hip.security.deid",
]


@pytest.mark.parametrize("module_name", SCAFFOLD_MODULES)
def test_module_imports(module_name: str) -> None:
    """Each scaffold module imports without error."""
    assert importlib.import_module(module_name) is not None


def test_version_exposed() -> None:
    """The package advertises a version string."""
    import hip

    assert isinstance(hip.__version__, str)


def test_platform_shim_does_not_shadow_stdlib() -> None:
    """The stdlib ``platform`` module is still reachable, not shadowed by ours."""
    import platform as stdlib_platform

    assert hasattr(stdlib_platform, "system")


def test_project_root_resolves_to_repo() -> None:
    """The pathlib-based project_root points at the repository root."""
    from hip.platform.paths import project_root

    root = project_root()
    assert (root / "pyproject.toml").is_file()
    assert (root / "src" / "hip").is_dir()
