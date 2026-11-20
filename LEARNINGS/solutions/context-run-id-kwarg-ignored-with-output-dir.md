# NodeExecutionContext without a request reads run_id from the folder name

Without a request, `NodeExecutionContext.run_id` (Python) / `runId` (TS)
returns the **parent folder name of `output_dir`**; the `run_id=` / `runId`
argument only shapes the default folder when no `output_dir` is passed.
A test that passes both gets the folder name, not the argument (#278: the
golden result file came out with `workflow_run_id: "tmp"`).

Fix in tests: build the context as
`NodeExecutionContext(output_dir=root / "<run-id>" / "<node-id>")`.
Production contexts always carry a request, so real runs are unaffected.
