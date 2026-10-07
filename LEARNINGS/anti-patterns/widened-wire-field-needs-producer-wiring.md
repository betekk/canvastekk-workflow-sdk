# A widened wire field needs a producer, not just a parse seam

**Source:** #3498 code review (canvastekk-workflow-sdk) · **Date:** 2026-10-07 · **Confidence:** high

Widening the inbound parse schema AND adopting the field in the handler (the
`parity-port-must-widen-wire-schema` rule) is necessary but not sufficient for
a propagation fix — verify a **producer** actually threads the field to that
seam. #3498 added `execution_id` to both SDK schemas plus `run()` adoption,
while the ECS dispatcher transports the id as an env var beside the JSON
payload (`REQUEST_JSON` never carries it), so the 403 bug persists until the
runner merges `env.EXECUTION_ID` into the parsed request (#3501). Rule: grep
the producer side for the field before declaring a propagation ticket fixed;
env-var transport beside a JSON payload is the tell.
