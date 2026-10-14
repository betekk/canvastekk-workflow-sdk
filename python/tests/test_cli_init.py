"""Tests pinning the `sdk init` scaffold destination.

The scaffold target is an API contract: DA-2982 moved it from
`.opencode/skills/` (OpenCode-only) to `.agents/skills/` (the Agent Skills
standard location discovered by OpenCode v2 AND pi). These tests fail if the
destination regresses.

Uses subprocess.run per the test_main.py convention: never import
canvastekk_workflow_sdk at module scope.
"""

import os
import subprocess
import sys
from pathlib import Path

PYTHON_BIN = Path(sys.executable)
REPO_PYTHON_DIR = Path(__file__).resolve().parents[1]


def _cli_env() -> dict[str, str]:
    """Env that forces the CLI subprocess to import THIS repo's SDK code."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    repo_dir = str(REPO_PYTHON_DIR)
    env["PYTHONPATH"] = f"{repo_dir}{os.pathsep}{existing}" if existing else repo_dir
    return env


def test_init_scaffolds_skills_into_agents_skills(tmp_path):
    """`init` scaffolds both bundled skills into .agents/skills/<id>/SKILL.md."""
    result = subprocess.run(
        [PYTHON_BIN, "-m", "canvastekk_workflow_sdk", "init"],
        cwd=tmp_path,
        env=_cli_env(),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    for skill_id in (
        "canvastekk-workflow-sdk-assistant",
        "canvastekk-node-builder",
        "canvastekk-node-patterns",
    ):
        scaffolded = tmp_path / ".agents" / "skills" / skill_id / "SKILL.md"
        assert scaffolded.is_file(), f"missing scaffold: {scaffolded}"


def test_init_does_not_create_legacy_opencode_skills(tmp_path):
    """The legacy .opencode/skills destination must not be recreated."""
    result = subprocess.run(
        [PYTHON_BIN, "-m", "canvastekk_workflow_sdk", "init"],
        cwd=tmp_path,
        env=_cli_env(),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / ".opencode" / "skills").exists(), (
        "init recreated the legacy .opencode/skills destination"
    )
