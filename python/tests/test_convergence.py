"""Tests for the registry-convergence CLI command (DA-3086).

Ported 1:1 from the absorbed in-repo test suites (DA-3070/DA-3071/DA-3084)
minus the per-repo slug-file drift guards, which are repo-specific and stay
in the consuming repos. Covers the four-clause drain predicate and the
presence-only staged assert against the POST-drain snapshot.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from canvastekk_workflow_sdk.convergence import (
    _delete,
    assert_staged,
    canonical_from_invoke_url,
    compute_drain,
    drain,
    fetch_actives,
    history_slugs,
    load_declared,
)

INVOKE_BASE = "https://nodes.lambda-url.ap-southeast-1.on.aws"


def _node(slug: str, invoke_base: str | None = INVOKE_BASE) -> dict:
    """A registry active whose invoke_url belongs to invoke_base (or elsewhere)."""
    if invoke_base is None:
        return {"name": f"{slug}-x", "slug": slug, "invoke_url": None}
    base = invoke_base.rstrip("/")
    return {
        "name": f"{slug}-lambda",
        "slug": f"{slug}-lambda",
        "invoke_url": f"{base}/nodes/{slug}/execute",
    }


class TestCanonicalFromInvokeUrl:
    def test_matches_this_deploy(self):
        assert canonical_from_invoke_url(f"{INVOKE_BASE}/nodes/cds-file/execute", INVOKE_BASE) == "cds-file"

    def test_rejects_other_invoke_base(self):
        assert (
            canonical_from_invoke_url(
                "https://other.lambda-url.on.aws/nodes/cds-file/execute",
                INVOKE_BASE,
            )
            is None
        )

    def test_rejects_non_execute_path(self):
        assert canonical_from_invoke_url(f"{INVOKE_BASE}/nodes/cds-file/manifest", INVOKE_BASE) is None

    def test_rejects_none(self):
        assert canonical_from_invoke_url(None, INVOKE_BASE) is None


class TestComputeDrain:
    def test_drains_history_declared_file_removed_owned(self):
        actives = [_node("legacy-old-check")]
        drain = compute_drain(
            actives,
            history={"legacy-old-check", "cds-file"},
            declared={"cds-file"},
            invoke_base=INVOKE_BASE,
        )
        assert [n["name"] for n in drain] == ["legacy-old-check-lambda"]

    def test_never_drains_slug_still_in_file(self):
        actives = [_node("cds-file")]
        drain = compute_drain(
            actives,
            history={"cds-file"},
            declared={"cds-file", "cds-other"},
            invoke_base=INVOKE_BASE,
        )
        assert drain == []

    def test_never_drains_foreign_registration(self):
        actives = [
            _node("legacy-old-check", invoke_base="https://ifc.lambda-url.on.aws"),
            _node("legacy-no-invoke", invoke_base=None),
        ]
        drain = compute_drain(
            actives,
            history={"legacy-old-check", "legacy-no-invoke"},
            declared=set(),
            invoke_base=INVOKE_BASE,
        )
        assert drain == []

    def test_ignores_never_declared_actives(self):
        actives = [_node("cds-file")]
        drain = compute_drain(
            actives,
            history={"legacy-old-check"},
            declared=set(),
            invoke_base=INVOKE_BASE,
        )
        assert drain == []


class TestAssertStaged:
    def test_passes_when_all_staged_present(self):
        actives = [_node("test-a"), _node("test-b")]
        assert_staged(["test-a", "test-b"], actives, INVOKE_BASE)

    def test_fails_loudly_on_missing(self):
        actives = [_node("test-a")]
        with pytest.raises(SystemExit) as exc:
            assert_staged(["test-a", "test-missing"], actives, INVOKE_BASE)
        assert exc.value.code == 1

    def test_staged_single_on_main(self):
        actives = [_node("cds-file")]
        assert_staged(["cds-file"], actives, INVOKE_BASE)


def _init_git_repo(path: Path, versions: list[str]) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "init", "-q"], cwd=path, check=True, env=env)
    for i, content in enumerate(versions):
        (path / "node-slugs.txt").write_text(content)
        subprocess.run(["git", "add", "node-slugs.txt"], cwd=path, check=True, env=env)
        subprocess.run(
            ["git", "commit", "-qm", f"v{i}", "--allow-empty"],
            cwd=path,
            check=True,
            env=env,
        )


class TestHistorySlugs:
    def test_union_of_versions(self, tmp_path):
        _init_git_repo(tmp_path, ["test-a\ntest-b\n", "test-a\n"])
        assert history_slugs(tmp_path / "node-slugs.txt") == {"test-a", "test-b"}

    def test_single_version(self, tmp_path):
        _init_git_repo(tmp_path, ["# comment\ntest-a\n\n"])
        assert history_slugs(tmp_path / "node-slugs.txt") == {"test-a"}


class TestLoadDeclared:
    def test_comments_and_blanks_ignored(self, tmp_path):
        f = tmp_path / "node-slugs.txt"
        f.write_text("# header\ntest-a\n\n  \ntest-b\n")
        assert load_declared(f) == ["test-a", "test-b"]


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _page(nodes, number, total_pages):
    return {
        "content": nodes,
        "page": {
            "size": 100,
            "number": number,
            "total_elements": len(nodes),
            "total_pages": total_pages,
        },
    }


class TestFetchActives:
    def test_paginates_all_pages(self, monkeypatch):
        pages = [
            _page([{"name": "a-lambda", "invoke_url": None}], 0, 2),
            _page([{"name": "b-lambda", "invoke_url": None}], 1, 2),
        ]
        seen = []

        def fake_urlopen(req, timeout):
            seen.append(req.full_url)
            return _FakeResponse(pages[len(seen) - 1])

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        actives = fetch_actives("https://cwe.example", "tok")
        assert [n["name"] for n in actives] == ["a-lambda", "b-lambda"]
        assert "page=0" in seen[0] and "page=1" in seen[1]

    def test_missing_page_fields_default_to_one_page(self, monkeypatch):
        monkeypatch.setattr(
            urllib.request,
            "urlopen",
            lambda req, timeout: _FakeResponse({"content": [{"name": "x"}], "page": {}}),
        )
        assert [n["name"] for n in fetch_actives("https://cwe.example", "tok")] == ["x"]


class TestDeleteIdempotency:
    def test_404_swallowed(self, monkeypatch):
        def fake_urlopen(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 404, "not found", None, io.BytesIO(b""))

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        _delete("https://cwe.example/api/workflows/nodes/by-name/gone", "tok")

    def test_500_raises(self, monkeypatch):
        def fake_urlopen(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 500, "boom", None, io.BytesIO(b""))

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(urllib.error.HTTPError):
            _delete("https://cwe.example/api/workflows/nodes/by-name/x", "tok")


class TestDrain:
    def test_deletes_each_candidate_by_name_url_encoded(self, monkeypatch):
        deleted = []

        def fake_urlopen(req, timeout):
            deleted.append(req.full_url)
            return _FakeResponse({"message": "ok"})

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        records = [{"name": "legacy-old-lambda"}, {"name": "weird/slug"}]
        drain("https://cwe.example", "tok", records, dry_run=False)
        assert deleted == [
            "https://cwe.example/api/workflows/nodes/by-name/legacy-old-lambda",
            "https://cwe.example/api/workflows/nodes/by-name/weird%2Fslug",
        ]

    def test_dry_run_makes_no_requests(self, monkeypatch, capsys):
        def fake_urlopen(req, timeout):
            raise AssertionError("dry-run must not hit the API")

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        drain("https://cwe.example", "tok", [{"name": "legacy-old-lambda"}], dry_run=True)
        assert "would soft-retire" in capsys.readouterr().out
