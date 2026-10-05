"""DA-3425: bump_versions.py must stamp the _version.py leaf.

The 0.37.1 wheel shipped with METADATA 0.37.1 but an internal
``__version__ = "0.37.0"`` — the release bump script never touched the
DA-3359 leaf module (the manifest-stamp source of truth). These tests pin
the stamping contract: version AND RELEASE_DATE land in the leaf, alongside
the classic targets.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "bump_versions.py"


def _make_fixture_tree(root: Path) -> None:
    leaf_dir = root / "python" / "canvastekk_workflow_sdk"
    leaf_dir.mkdir(parents=True)
    (leaf_dir / "_version.py").write_text('__version__ = "0.0.1"\n\nRELEASE_DATE = "2000-01-01"\n', encoding="utf-8")
    (root / "python" / "pyproject.toml").write_text(
        '[tool.poetry]\nname = "canvastekk-workflow-sdk"\nversion = "0.0.1"\n',
        encoding="utf-8",
    )
    ts_dir = root / "typescript" / "src"
    ts_dir.mkdir(parents=True)
    (ts_dir.parent / "package.json").write_text(
        json.dumps({"name": "@betekk/canvastekk-workflow-sdk", "version": "0.0.1"}),
        encoding="utf-8",
    )
    (ts_dir / "version.ts").write_text('export const VERSION = "0.0.1";\n', encoding="utf-8")


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )


def test_leaf_gets_version_and_release_date(tmp_path: Path) -> None:
    """Explicit date arg stamps both leaf strings (DA-3425 contract)."""
    _make_fixture_tree(tmp_path)
    result = _run(tmp_path, "9.9.9", "2030-05-06")

    leaf = (tmp_path / "python" / "canvastekk_workflow_sdk" / "_version.py").read_text(encoding="utf-8")
    assert '__version__ = "9.9.9"' in leaf
    assert 'RELEASE_DATE = "2030-05-06"' in leaf

    # The summary line must name the leaf entry — fails if anyone drops
    # python_version_leaf from VERSION_FILES again.
    assert "python_version_leaf" in result.stdout


def test_release_date_defaults_to_today_utc(tmp_path: Path) -> None:
    """No date arg → RELEASE_DATE defaults to today (UTC)."""
    _make_fixture_tree(tmp_path)
    _run(tmp_path, "9.9.9")

    leaf = (tmp_path / "python" / "canvastekk_workflow_sdk" / "_version.py").read_text(encoding="utf-8")
    today = datetime.now(UTC).date().isoformat()
    assert f'RELEASE_DATE = "{today}"' in leaf


def test_classic_targets_still_stamped(tmp_path: Path) -> None:
    """pyproject / package.json / version.ts keep their stamps (no regressions)."""
    _make_fixture_tree(tmp_path)
    _run(tmp_path, "8.8.8", "2030-01-01")

    pyproject = (tmp_path / "python" / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "8.8.8"' in pyproject
    package = json.loads((tmp_path / "typescript" / "package.json").read_text(encoding="utf-8"))
    assert package["version"] == "8.8.8"
    version_ts = (tmp_path / "typescript" / "src" / "version.ts").read_text(encoding="utf-8")
    assert 'export const VERSION = "8.8.8"' in version_ts


@pytest.mark.parametrize("bad", ["notaversion", "1.2"])
def test_invalid_version_rejected(tmp_path: Path, bad: str) -> None:
    """Garbage versions exit non-zero without writing stamps."""
    _make_fixture_tree(tmp_path)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), bad],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    leaf = (tmp_path / "python" / "canvastekk_workflow_sdk" / "_version.py").read_text(encoding="utf-8")
    assert '__version__ = "0.0.1"' in leaf
