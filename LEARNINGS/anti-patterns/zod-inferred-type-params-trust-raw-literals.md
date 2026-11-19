# Zod-Inferred Type Params Trust Raw Literals at Payload Boundaries

**Category**: anti-patterns · **Confidence**: High · **Scope**: canvastekk-workflow-sdk typescript (generalizes to zod codebases)
**Date**: 2026-11-19 · **Ticket**: betekk/canvastekk-workflow-sdk#257

`type WorkflowNodeManifest = z.infer<typeof WorkflowNodeManifestSchema>` is
structural: an object literal satisfies it with **zero runtime validation**.
When a public function's param is the inferred type (ts `registry.ts:106`
`buildRegistryPayload(definition: WorkflowNodeManifest, ...)`) and the schema's
real validation lives in a lazy `superRefine`/transform, only explicit
`.parse()` sites enforce it. Pre-#257 exactly one eager parse existed
(`cli.ts`); `registerNode` shipped raw literals to the registry unvalidated —
the parse-site gap the architecture review caught (folded into PLAN-257 step
2.1, fix at `typescript/src/registry.ts:228`).

Rule: in zod codebases, every entrypoint that crosses a trust boundary (network
POST, file write consumed downstream) must call `Schema.parse()` on its
inferred-type param — the inferred type is a compile-time courtesy, not a
runtime guarantee. `exportDefinition` (`registry.ts:300`) still exports
unvalidated literals to JSON; harmless today only because every consumer
re-parses.
