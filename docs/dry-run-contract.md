# Dry-Run Contract (D10, #111)

The `dry_run` request flag asks a node for a **validation-only execution**: the
full input-validation path runs, but no work happens. It is the safe positive
path that CI and the engine's conformance probe (#112/#113) rely on.

This document is normative for **self-hosted implementers** — authors whose
nodes do not use the SDK's `BaseNode`/`create_node_app` (Flask, Django, Hono,
anything). If your node is built on the SDK, `dry_run` is already implemented;
you only need the declaration (below).

## Declaring the capability

A node opts in via its served manifest's contract (D8/#110):

```json
{
  "contract": {
    "transport": "http",
    "routes": ["/execute", "/health", "/manifest"],
    "capabilities": { "dry_run": true },
    "openapi": "3.2"
  }
}
```

A node that does NOT declare `capabilities.dry_run` must REJECT a dry-run
request with a structured failure — `status: "fail"`,
`error_code: "DRY_RUN_NOT_SUPPORTED"`, `dry_run: true` — never a silent
normal execution. The SDK harness does this for you.

## The wire contract

Request: `POST /execute` with a top-level boolean field:

```json
{ "run_id": "...", "node_id": "...", "inputs": { ... }, "dry_run": true }
```

Response (valid inputs, capability declared):

```json
{
  "status": "pass",
  "execution_id": "dryrun-<original-id>",
  "outputs": {},
  "token_usage": 0.0,
  "dry_run": true
}
```

## What a dry run MUST do

1. **Validate inputs fully** — exactly as a real execution would; invalid
   inputs fail with the normal validation error BEFORE any dry-run logic.
2. **Check the capability** — only a node whose manifest declares
   `capabilities.dry_run` may answer a dry-run request with a pass.
3. **Respond pass on valid inputs** — `status: "pass"`, `outputs: {}`,
   `token_usage: 0`, and an `execution_id` namespaced with the `dryrun-`
   prefix.
4. **Echo the flag** — `dry_run: true` on the response (including the
   structured refusal above), so callers can distinguish synthetic passes.

## What a dry run MUST NOT do

1. **Call the node handler** — no `execute()` invocation, ever.
2. **Perform file I/O** — no downloads of input files, no writes to output
   directories.
3. **Upload anything** — a dry-run pass must never trigger output uploads,
   even when `output_upload_url` is present.
4. **Bill or count tokens** — `token_usage` is exactly `0.0`; no metering,
   no quota consumption.
5. **Mutate state** — no database writes, no messages sent, no external side
   effects of any kind.

## Branch position (SDK harness reference)

The SDK's harness branches AFTER full input validation and BEFORE context
creation, file downloads, middleware, execution, and upload. Position is the
guarantee: moving the branch after any side-effecting step breaks this
contract. Self-hosted implementers should place their dry-run branch at the
same point.

## Who consumes this

- The engine's registration-time conformance gate (`register_node(verify=True)`)
  and the SDK verifier's positive probe (`verify --dry-run`, #113) — both send
  `dry_run: true` and expect the synthetic pass above.
- CI pipelines that want a deploy check with zero side effects.
