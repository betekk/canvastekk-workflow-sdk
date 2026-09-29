# TS Method-Syntax Bivariance Keeps Additive Parameter Widening Safe for Implementors

**Category:** patterns · **Scope:** TypeScript public interfaces · **Date:** 2026-09-29

## The pattern

Widening a method PARAMETER to a union (`uploadFile(filePath, target: string)` → `target: string | UploadSessionDescriptor`) stays additive for existing implementors because TS **method-syntax declarations remain parameter-bivariant** even under `strictFunctionTypes` — a legacy implementation taking the narrower `string` still satisfies the widened interface.

The trap: converting the interface member to a **property-arrow signature** (`uploadFile: (filePath: string, target: X) => Promise<void>`) applies strict contravariance and breaks every legacy implementor. Keep interface members as method syntax when you intend additive widening.

## Pin

`tsconfig.json` excludes `tests/` from typecheck, so a type-fixture must be checked via a dedicated config (`tsconfig.tests.json` extends the base with `rootDir: "."` + a narrow include; script `typecheck:tests`). Fixture: `tests/legacy-uploader-fixture.ts` (DA-3314) — assignment of a legacy-only implementor to the widened interface is the assertion.
