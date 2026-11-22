# Result file schemas

Canonical, published JSON Schemas (draft-07) for workflow run result files
(#278, epic betekk/canvastekk-tracker#4309). Guide: [`docs/RESULT-FILE.md`](../../docs/RESULT-FILE.md).

| File | Describes |
|---|---|
| `1.0.0.json` | The file layout 1.0.0 (header keys, `summary` rules, `body`) |
| `end-value-1.0.0.json` | The value of the reserved `__end__.result_file` key (engine storage pointer) |
| `1.1.0.json` | Layout 1.1.0: 1.0.0 plus optional `workflow_definition`, `inputs` and `verdict` (#283) |
| `golden/` | Shared input and expected bytes; the Python and TypeScript writers must reproduce `expected.json` and `expected-1.1.0.json` exactly |

Copies: the Python wheel ships these under
`python/canvastekk_workflow_sdk/data/schemas/result-file/`, and the TypeScript
package embeds them in `typescript/src/result-file.ts`. Tests in both
runtimes fail when a copy drifts from this folder.

Never edit a released schema in place; add a new version file.
