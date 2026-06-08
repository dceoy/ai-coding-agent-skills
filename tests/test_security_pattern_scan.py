"""Tests for the security-guidance pattern scan helper."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/security-guidance/scripts/security_pattern_scan.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("security_pattern_scan", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_self_check_passes() -> None:
    """Built-in self-checks for custom rules and secret scanning should pass."""
    module = _load_module()
    assert module.run_self_checks() == 0
