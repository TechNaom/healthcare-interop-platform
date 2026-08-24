"""Path helpers — ``pathlib`` only, never raw string paths (ADR-003).

Centralizes filesystem-location logic so no module hardcodes an OS-specific
path. Kept deliberately tiny at Phase 0; grows as real components need
locations (config dirs, file-drop inboxes, fixture roots).
"""

from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    """Repository root, derived from this file's location.

    Independent of the current working directory or OS path separator.
    """
    return Path(__file__).resolve().parents[3]
