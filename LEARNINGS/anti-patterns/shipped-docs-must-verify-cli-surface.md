# Shipped Skill/Doc Content Must Verify CLI Claims Against the Dispatch Surface

**Category**: anti-pattern
**Confidence**: 0.9
**Scope**: project
**Date**: 2026-10-14
**Source**: #144 review — assistant skill AUDIT section

## Anti-pattern

Shipped teaching content (skills, READMEs, guides) inventing CLI commands
that sound right. Found in #144: the AUDIT section taught
`python -m canvastekk_workflow_sdk export_definition handler:definition
--output new.json` — no `export` subcommand exists. The real surface is
`validate | diff | init | --version | --help` (`__main__.py` main());
`export_definition` is a package-root Python function taking
`(definition, output_path)`.

Every user following the fabricated command hits an error on first use —
trust in the whole skill drops with it.

## Fix direction

Before shipping any command snippet, grep the dispatch surface it claims to
ride (`__main__.py` subcommands, `package.json` scripts, Makefile targets)
and prefer a verified real invocation (here: a `python -c` one-liner calling
the actual function) over a plausible-looking flag combination.
