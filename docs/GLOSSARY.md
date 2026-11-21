# CanvasTEKK Workflow SDK — Glossary

The vocabulary law for this SDK and its dependents (from epic
[betekk/canvastekk-tracker#4301](https://github.com/betekk/canvastekk-tracker/issues/4301)).
One rule: **"definition" only ever means a workflow definition; node-level
things say "manifest"; every module, type, class, function and constant names
the object it belongs to.**

| Term | Means |
|---|---|
| Workflow definition | The graph a user saves (nodes + edges); has a lifecycle status |
| Workflow definition node | One step placed inside a workflow definition |
| Workflow node manifest | What a deployable node publishes about itself (slug, version, schemas, contract) |
| Workflow node | The serving runtime (base class, app, registry, conformance) |
| Workflow run | One execution of a workflow definition |
| Workflow run id | The run's one identifier (`workflow_runs.id` in CWE; also the Temporal workflow id since CWE#1440). Nodes receive it as the wire `run_id` and, once CWE#1443 ships, inside the versioned `run_context` object |
| Run context (`run_context`) | Versioned run identity the engine sends with every `/execute` (#281, CWE#1443): `run_context_version`, `workflow_run_id`, definition id/slug/version, `account_id`, `started_at`. Exposed on the node execution context (`ctx.run_context` / `ctx.runContext`); `None`/`null` when the engine sends none. Additive keys bump the minor |
| Node execution / node call | One call to a node (request, response, context, call outcome, protocol) |
| Node I/O data | Shared payload types (Point3D, Plane, ...) |
| Workflow run result file | One JSON file per run in the platform layout (`result_file_version`, labels, `summary`, `body`), written by the producing node through the SDK writer; see [`RESULT-FILE.md`](./RESULT-FILE.md). Not called a "manifest" |

Renaming rollout: SDK renames modules and public names in Python and
TypeScript, keeps the old names as deprecated aliases, releases **0.67.0**
(non-breaking) — issue
[#271](https://github.com/betekk/canvastekk-workflow-sdk/issues/271).
Consumer repos migrate on their own tickets; SDK **1.0.0** (#272) removes the
aliases once no consumer uses an old name. See
[`adr/0001-explicit-node-naming.md`](./adr/0001-explicit-node-naming.md) for
the complete rename map.
