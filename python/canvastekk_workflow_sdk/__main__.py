"""CLI tools for canvastekk-workflow-sdk.

Usage:
    python -m canvastekk_workflow_sdk validate <module_path> [--json]
    python -m canvastekk_workflow_sdk registry-convergence --registry-base URL --invoke-base URL --slugs-file PATH
    python -m canvastekk_workflow_sdk init [--agents-md] [--force]
"""

from __future__ import annotations

import importlib
import json
import re
import shutil
import sys
from importlib.resources import as_file
from importlib.resources import files as pkg_files
from pathlib import Path

from jsonschema import Draft7Validator
from jsonschema import exceptions as _jsonschema_exceptions


def _load_definition(module_path: str):
    """Load a WorkflowNodeManifest from a module:attribute path."""
    if ":" not in module_path:
        raise ValueError(f"Invalid path '{module_path}'. Use 'module:attribute' format (e.g., 'handler:definition').")

    module_name, attr_name = module_path.rsplit(":", 1)
    module = importlib.import_module(module_name)
    definition = getattr(module, attr_name)

    from canvastekk_workflow_sdk.definition import WorkflowNodeManifest

    if not isinstance(definition, WorkflowNodeManifest):
        raise TypeError(f"Expected WorkflowNodeManifest, got {type(definition).__name__}")

    return definition


def _validate_definition(definition) -> dict:
    """Inspect a validated WorkflowNodeManifest and return a diagnostic report.

    The Pydantic ``model_validator`` has already checked format/type
    constraints.  This function inspects file fields for recommended
    ``x-*`` extensions and builds a human-readable report.

    Args:
        definition: A fully-validated :class:`WorkflowNodeManifest` instance.

    Returns:
        A dict with keys ``valid``, ``errors``, ``warnings``,
        ``file_input_fields``, and ``file_output_fields``.
    """
    report = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "file_input_fields": [],
        "file_output_fields": [],
        "slug": definition.slug,
        "version": definition.version,
        "id": definition.id,
    }

    # The model_validator already ran at definition time.
    # If we got here, basic format validation passed.

    for name in definition.file_input_fields:
        schema = definition.input_schema.get("properties", {}).get(name, {})
        field_report = {"name": name, "format": schema.get("format"), "type": schema.get("type")}

        extensions = {}
        if "x-accept" in schema:
            extensions["x-accept"] = schema["x-accept"]
        else:
            report["warnings"].append(f"File input field '{name}' has no x-accept extension (recommended)")

        if "x-maxSizeBytes" in schema:
            extensions["x-maxSizeBytes"] = schema["x-maxSizeBytes"]
        else:
            report["warnings"].append(f"File input field '{name}' has no x-maxSizeBytes extension (recommended)")

        field_report["extensions"] = extensions
        report["file_input_fields"].append(field_report)

    for name in definition.file_output_fields:
        schema = definition.output_schema.get("properties", {}).get(name, {})
        field_report = {"name": name, "format": schema.get("format"), "type": schema.get("type")}
        report["file_output_fields"].append(field_report)

    # Draft-7 structural validation of the JSON schemas (DA-1955).
    # Catches broken schemas at authoring time instead of at engine registration.
    for label, schema in (("input_schema", definition.input_schema), ("output_schema", definition.output_schema)):
        try:
            Draft7Validator.check_schema(schema)
        except _jsonschema_exceptions.SchemaError as exc:
            report["valid"] = False
            report["errors"].append(f"{label} is not a valid draft-7 JSON schema: {exc.message}")

    return report


# Engine registration request whitelist — mirrors the engine's
# CreateWorkflowNodeRequest (see canvastekk-workflow-engine
# schemas/api/nodes.py and the CI register path in
# canvastekk-workflow-nodes deploy-lambda.yml). DA-2603/DA-2666.
_ENGINE_REQUEST_ALLOWED = frozenset(
    {
        "name",
        "version",
        "label",
        "description",
        "input_schema",
        "output_schema",
        "invoke_type",
        "invoke_url",
        "invoke_config",
        "category",
        "tags",
        "styles",
        "constraints",
        "token_cost",
        "timeout_seconds",
        "deprecation",
    }
)
_ENGINE_REQUEST_REQUIRED = ("name", "version", "label", "description", "input_schema", "output_schema")


_ENGINE_NAME_PATTERN = r"[a-zA-Z0-9_-]+"
_ENGINE_CATEGORIES = frozenset(
    {"control", "utility", "io", "conversion", "measurement", "geometry", "inspection", "ai", "custom"}
)
_ENGINE_MAX_TIMEOUT_SECONDS = 86400


def _build_engine_request(definition, *, invoke_url: str | None = None, name_suffix: str = "") -> dict:
    """Map a canonical manifest to the engine registration request.

    Delegates the field mapping to the shipped, engine-boundary-tested
    ``build_registry_payload`` (single source of truth — the engine request
    is ``extra="forbid"``), then applies the CLI-only name suffix.
    """
    from canvastekk_workflow_sdk.registry import build_registry_payload

    payload = build_registry_payload(definition, invoke_url=invoke_url)
    if name_suffix:
        payload["name"] = definition.slug + name_suffix
    return payload


def _probe_definition(definition, *, name_suffix: str = "") -> dict:
    """Offline registration probes: 'passes locally ⇔ passes registration'.

    Runs the manifest probes from ``_validate_definition`` (model format,
    draft-7 schemas, file-field extensions) plus the engine-request mirror:
    the mapped payload must carry exactly the required keys, no client-side
    ``slug`` key, no keys outside the engine whitelist, and values inside the
    engine's request domain (category enum, timeout ceiling, name pattern —
    mirroring the engine's RegisterWorkflowNodeRequest validators).

    Strictly stricter than registration: the host-ceiling probe rejects
    budgets above the node's own ``hard_max_runtime_seconds`` which the
    engine itself would accept, so passing here implies passing registration
    (not biconditional).
    """
    report = _validate_definition(definition)
    report["probes"] = ["manifest", "engine-request-mirror", "host-ceiling"]

    payload = _build_engine_request(definition, name_suffix=name_suffix)
    missing = [k for k in _ENGINE_REQUEST_REQUIRED if payload.get(k) in (None, "", [], {})]
    if missing:
        report["valid"] = False
        report["errors"].append(f"Engine request missing required keys: {missing}")
    if "slug" in payload:
        report["valid"] = False
        report["errors"].append("Engine request must not carry a client-set 'slug' key (engine rejects it)")
    extra = sorted(set(payload) - _ENGINE_REQUEST_ALLOWED)
    if extra:
        report["valid"] = False
        report["errors"].append(f"Engine request carries keys outside the engine whitelist: {extra}")
    if definition.category not in _ENGINE_CATEGORIES:
        report["valid"] = False
        report["errors"].append(
            f"category {definition.category!r} is outside the engine's enum {_ENGINE_CATEGORIES}"
        )
    if definition.timeout_seconds > _ENGINE_MAX_TIMEOUT_SECONDS:
        report["valid"] = False
        report["errors"].append(f"timeout_seconds {definition.timeout_seconds} exceeds the engine ceiling 86400")
    if definition.timeout_seconds > definition.hard_max_runtime_seconds:
        report["valid"] = False
        report["errors"].append(
            f"timeout_seconds {definition.timeout_seconds} exceeds the node's "
            f"hard_max_runtime_seconds {definition.hard_max_runtime_seconds}"
        )
    if not re.fullmatch(_ENGINE_NAME_PATTERN, str(payload.get("name", ""))):
        report["valid"] = False
        report["errors"].append(f"engine name {payload.get('name')!r} does not match {_ENGINE_NAME_PATTERN}")
    return report


def _manifest_from_source(source: str):
    """Load a WorkflowNodeManifest from a JSON file path or http(s) URL.

    Returns the definition, or an int exit code (2) on failure with the
    error printed.
    """
    import urllib.request

    try:
        if re.match(r"^https?://", source):
            with urllib.request.urlopen(source, timeout=30) as resp:
                raw = json.loads(resp.read())
        else:
            with open(source, encoding="utf-8") as f:
                raw = json.load(f)
        from canvastekk_workflow_sdk.definition import WorkflowNodeManifest

        return WorkflowNodeManifest(**raw)
    except Exception as e:
        print(f"Error loading manifest from {source}: {e}", file=sys.stderr)
        return 2


def _run_register(args: list[str]) -> int:
    """Register a node manifest against the engine from CI.

    Mirrors the proven service-identity path (deploy-lambda.yml): POST the
    mapped payload to ``{engine}/api/workflows/nodes/`` with the
    ``X-Service-Token`` header, then verify via ``by-name/{name}``.

    Exit codes: 0 ok · 2 usage · 3 auth (401/403) · 4 other 4xx · 5 5xx ·
    6 network. The token is read from ``CANVASTEKK_REGISTRY_TOKEN`` and is
    never printed.
    """
    import os
    import urllib.error
    import urllib.parse
    import urllib.request

    def _usage() -> int:
        print(
            "Usage: register <module:attribute> | --manifest <file.json|URL> "
            "--engine-url URL [--invoke-url URL] [--name-suffix S] [--json]",
            file=sys.stderr,
        )
        return 2

    def _flag(name: str) -> str | None:
        for i, a in enumerate(args):
            if a == name and i + 1 < len(args):
                return args[i + 1]
            if a.startswith(name + "="):
                return a.split("=", 1)[1]
        return None

    module_path = args[0] if args and not args[0].startswith("--") else None
    manifest_source = _flag("--manifest")
    engine_url = _flag("--engine-url")
    if (not module_path and not manifest_source) or not engine_url:
        return _usage()

    token = os.environ.get("CANVASTEKK_REGISTRY_TOKEN", "")
    if not token:
        print("Error: CANVASTEKK_REGISTRY_TOKEN is not set (service credential)", file=sys.stderr)
        return 2

    name_suffix = _flag("--name-suffix") or ""
    if name_suffix and not re.fullmatch(_ENGINE_NAME_PATTERN, name_suffix):
        print(f"Error: --name-suffix {name_suffix!r} does not match {_ENGINE_NAME_PATTERN}", file=sys.stderr)
        return 2

    use_json = "--json" in args
    if manifest_source:
        # DA-2604: --manifest <file.json|URL> — parity with the ts CLI; CI
        # cannot import module:attribute from a deployed Lambda, so the
        # manifest is fetched to a file (or URL) and loaded directly.
        definition = _manifest_from_source(manifest_source)
        if isinstance(definition, int):
            return definition
    else:
        try:
            definition = _load_definition(module_path)
        except Exception as e:
            print(f"Error loading definition: {e}", file=sys.stderr)
            return 2

    payload = _build_engine_request(
        definition,
        invoke_url=_flag("--invoke-url"),
        name_suffix=name_suffix,
    )
    base = engine_url.rstrip("/") + "/api/workflows/nodes/"

    def _request(method: str, url: str, body: bytes | None = None):
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("X-Service-Token", token)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()

    def _exit(code: int, message: str, extra: dict | None = None) -> int:
        if use_json:
            out = {"ok": code == 0, "message": message, **(extra or {})}
            print(json.dumps(out, indent=2))
        else:
            stream = sys.stdout if code == 0 else sys.stderr
            print(message, file=stream)
        return code

    try:
        status, body = _request("POST", base, json.dumps(payload).encode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        if e.code in (401, 403):
            return _exit(3, f"Auth failed (HTTP {e.code}) for {payload['name']}")
        if 400 <= e.code < 500:
            return _exit(4, f"Rejected (HTTP {e.code}): {detail}", {"name": payload["name"]})
        return _exit(5, f"Engine error (HTTP {e.code}): {detail}")
    except (urllib.error.URLError, OSError) as e:
        return _exit(6, f"Network error reaching {base}: {e}")

    if not 200 <= status < 300:
        return _exit(5, f"Unexpected HTTP {status} from engine")

    try:
        status, body = _request("GET", base + "by-name/" + urllib.parse.quote(payload["name"]))
        node_id = json.loads(body).get("id", "")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError):
        node_id = ""

    return _exit(0, f"Registered {payload['name']} v{payload['version']}", {"id": node_id})


_CONTENT_MARKER = "CanvasTEKK Node Development"


def _read_data_file(relative_path: str) -> str:
    """Read a bundled data file from the installed package.

    Uses ``importlib.resources.as_file()`` to handle both directory-installed
    and zipped wheels correctly.

    Args:
        relative_path: Path relative to ``canvastekk_workflow_sdk/data/``.
    """
    try:
        ref = pkg_files("canvastekk_workflow_sdk.data").joinpath(relative_path)
    except ModuleNotFoundError:
        print("Error: SDK data package not found — reinstall canvastekk-workflow-sdk", file=sys.stderr)
        sys.exit(1)
    with as_file(ref) as real_path:
        return real_path.read_text(encoding="utf-8")


def _get_bundled_skills_dir():
    """Return a Traversable for the bundled skills directory."""
    try:
        return pkg_files("canvastekk_workflow_sdk.data").joinpath("skills")
    except ModuleNotFoundError:
        print("Error: SDK data package not found — reinstall canvastekk-workflow-sdk", file=sys.stderr)
        sys.exit(1)


def _init_skills(target_dir: Path, *, include_agents_md: bool = False, force: bool = False) -> None:
    """Copy bundled skill files into *target_dir*/.agents/skills/.

    Args:
        target_dir: Project root where .agents/ will be created.
        include_agents_md: Also write AGENTS.md in *target_dir*.
        force: Overwrite existing files without prompting.
    """
    with as_file(_get_bundled_skills_dir()) as skills_src:
        if not skills_src.is_dir():
            print("Error: bundled skills not found in package", file=sys.stderr)
            sys.exit(1)

        skills_dest = target_dir / ".agents" / "skills"
        created: list[str] = []
        skipped: list[str] = []

        for skill_dir in sorted(skills_src.iterdir()):
            if not skill_dir.is_dir():
                continue
            src_file = skill_dir / "SKILL.md"
            if not src_file.exists():
                continue

            skill_name = skill_dir.name
            if ".." in skill_name or "/" in skill_name or "\\" in skill_name:
                continue

            dest_file = skills_dest / skill_name / "SKILL.md"
            resolved = dest_file.resolve()
            if not str(resolved).startswith(str(skills_dest.resolve())):
                continue

            if dest_file.exists() and not force:
                skipped.append(str(dest_file.relative_to(target_dir)))
                continue

            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest_file)
            created.append(str(dest_file.relative_to(target_dir)))

        if not created and not skipped:
            print("Warning: No bundled skills found to install.", file=sys.stderr)

        if created:
            print(f"Created {len(created)} skill(s):")
            for path in created:
                print(f"  {path}")

        if skipped:
            print(f"Skipped {len(skipped)} existing file(s) (use --force to overwrite):")
            for path in skipped:
                print(f"  {path}")

    if include_agents_md:
        _write_agents_md(target_dir, force=force)

    print()
    print("Skills are loaded on-demand by coding agents.")
    print("Your agent will discover them automatically when you ask it to create a node.")


def _write_agents_md(target_dir: Path, *, force: bool = False) -> None:
    """Write or update AGENTS.md with CanvasTEKK skill routing rules."""
    agents_md_path = target_dir / "AGENTS.md"
    template = _read_data_file("templates/AGENTS.md")

    if force and agents_md_path.exists():
        agents_md_path.write_text(template)
        print(f"Overwrote {agents_md_path.relative_to(target_dir)}")
        return

    if not agents_md_path.exists():
        agents_md_path.write_text(template)
        print(f"Created {agents_md_path.relative_to(target_dir)}")
        return

    existing = agents_md_path.read_text()
    if _CONTENT_MARKER in existing:
        print("AGENTS.md already contains CanvasTEKK routing rules")
        return

    separator = "\n\n" if not existing.endswith("\n") else "\n"
    agents_md_path.write_text(existing + separator + template)
    print(f"Updated {agents_md_path.relative_to(target_dir)}")


def _load_manifest_file(path: str) -> dict:
    """Load a manifest dictionary from a JSON file.

    Args:
        path: Path to the JSON manifest file.

    Returns:
        The parsed manifest dictionary.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the content is not a JSON object.
        json.JSONDecodeError: If the content is not valid JSON.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(path)
    data = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"'{path}' does not contain a JSON object")
    return data


def _run_diff(args: list[str]) -> int:
    """Run the ``diff`` command: classify changes between two manifest files.

    Args:
        args: Positional file paths plus optional ``--json`` flag.

    Returns:
        Process exit code: 0 clean, 1 breaking change or diff error,
        2 load failure.
    """
    use_json = "--json" in args
    positional = [a for a in args if not a.startswith("--")]
    if len(positional) != 2:
        print("Error: diff requires two manifest files (old.json new.json)", file=sys.stderr)
        return 2

    old_path, new_path = positional
    try:
        old = _load_manifest_file(old_path)
        new = _load_manifest_file(new_path)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"Error loading manifests: {e}", file=sys.stderr)
        return 2

    from canvastekk_workflow_sdk.diff import diff_manifests

    result = diff_manifests(old, new)

    if use_json:
        from dataclasses import asdict

        print(json.dumps(asdict(result), indent=2))
    else:
        print(f"{old_path} -> {new_path}")
        print(f"  version: {result.old_version} -> {result.new_version} (bump: {result.version_bump or 'none'})")
        for change in result.breaking_changes:
            print(f"  BREAKING: {change}")
        for change in result.non_breaking_changes:
            print(f"  ok: {change}")
        for error in result.errors:
            print(f"  ERROR: {error}")
        if result.breaking:
            print()
            print("Breaking changes require a MAJOR version bump before registering.")
            print("On uat/prod the engine reseed additionally gates MAJOR+schema-diff upgrades")
            print("behind force_upgrade (update workflow-definitions.json, then POST")
            print("/api/internal/reseed?force_upgrade=true).")

    return 1 if (result.breaking or result.errors) else 0


def main() -> None:
    """CLI entry point for ``python -m canvastekk_workflow_sdk``.

    Supports:
      ``validate <module:attribute> [--json]`` — validate a node manifest.
      ``init [--agents-md] [--force]`` — scaffold agent skills into your project (.agents/skills).
      ``--version`` — print SDK version.
      ``--help`` — print usage information.
    """
    args = sys.argv[1:]

    if not args or args[0] == "--help":
        print("Usage: python -m canvastekk_workflow_sdk <command> [options]")
        print()
        print("Commands:")
        print("  validate <module:attribute> [--json]  Validate a node manifest definition")
        print("  probe <module:attribute> [--json]     Offline registration probes (validate + engine mirror)")
        print(
            "  register <module:attribute> --engine-url URL [--invoke-url URL] [--name-suffix S] [--json]"
        )
        print("                                        Publish the manifest to the engine registry")
        print(
            "  registry-convergence --registry-base URL --invoke-base URL --slugs-file PATH"
        )
        print("                                        [--staged S] [--dry-run] — drain retired slugs and assert staged presence")
        print("  diff <old.json> <new.json> [--json]   Classify breaking changes between manifests")
        print("  init [--agents-md] [--force]          Scaffold AI agent skills into your project")
        print(
            "  verify <url> [--api-key KEY] [--timeout S]  Probe a deployed node's HTTP contract"
        )
        print()
        print("Options:")
        print("  --json         Output validation results as JSON")
        print("  --agents-md    Also create AGENTS.md with skill routing rules")
        print("  --force        Overwrite existing files")
        print("  --version      Show SDK version")
        print("  --help         Show this help message")
        sys.exit(0)

    if args[0] == "--version":
        from canvastekk_workflow_sdk import __version__

        print(f"canvastekk-workflow-sdk {__version__}")
        sys.exit(0)

    if args[0] == "verify":
        url: str | None = None
        v_api_key: str | None = None
        v_timeout = 10.0
        v_rest = args[1:]
        i = 0
        while i < len(v_rest):
            if v_rest[i] == "--api-key" and i + 1 < len(v_rest):
                v_api_key = v_rest[i + 1]
                i += 2
            elif v_rest[i] == "--timeout" and i + 1 < len(v_rest):
                v_timeout = float(v_rest[i + 1])
                i += 2
            elif not url:
                url = v_rest[i]
                i += 1
            else:
                i += 1
        if not url:
            print("Usage: python -m canvastekk_workflow_sdk verify <url> [--api-key KEY] [--timeout S]", file=sys.stderr)
            sys.exit(2)
        from canvastekk_workflow_sdk.conformance import verify_node

        report = verify_node(url, timeout=v_timeout, api_key=v_api_key)
        print(report.summary())
        sys.exit(0 if report.ok else 1)

    if args[0] == "register":
        sys.exit(_run_register(args[1:]))

    if args[0] == "registry-convergence":
        from canvastekk_workflow_sdk.convergence import main as _convergence_main

        sys.exit(_convergence_main(args[1:]))

    if args[0] == "diff":
        sys.exit(_run_diff(args[1:]))

    if args[0] == "init":
        include_agents_md = "--agents-md" in args
        force = "--force" in args
        _init_skills(Path.cwd(), include_agents_md=include_agents_md, force=force)
        sys.exit(0)

    if args[0] not in ("validate", "probe"):
        print(f"Unknown command: {args[0]}", file=sys.stderr)
        sys.exit(1)

    if len(args) < 2 or args[1].startswith("--"):
        print("Error: module path required (e.g., handler:definition)", file=sys.stderr)
        sys.exit(2 if args[0] == "probe" else 1)

    module_path = args[1]
    use_json = "--json" in args

    # DA-2603: probe distinguishes usage/load failures (exit 2) from
    # validation failures (exit 1) — parity with the ts CLI. validate keeps
    # its historical single exit-1 contract.
    load_fail_code = 2 if args[0] == "probe" else 1

    try:
        definition = _load_definition(module_path)
    except Exception as e:
        if use_json:
            print(json.dumps({"valid": False, "errors": [str(e)], "warnings": []}, indent=2))
        else:
            print(f"Error loading definition: {e}", file=sys.stderr)
        sys.exit(load_fail_code)

    try:
        report_fn = _validate_definition if args[0] == "validate" else _probe_definition
        report = report_fn(definition)
    except Exception as e:
        report = {"valid": False, "errors": [str(e)], "warnings": []}

    if use_json:
        print(json.dumps(report, indent=2))
    else:
        if report["valid"]:
            print("PASS: Manifest is valid")
        else:
            print("FAIL: Manifest has errors")

        for error in report.get("errors", []):
            print(f"  ERROR: {error}")

        for warning in report.get("warnings", []):
            print(f"  WARN: {warning}")

        if report["file_input_fields"]:
            print(f"  File inputs: {[f['name'] for f in report['file_input_fields']]}")
        if report["file_output_fields"]:
            print(f"  File outputs: {[f['name'] for f in report['file_output_fields']]}")

    sys.exit(0 if report["valid"] else 1)


if __name__ == "__main__":
    main()
