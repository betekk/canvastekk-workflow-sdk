# Additive manifest fields crossing an extra=forbid request ride an existing free-form dict

A new optional manifest field that must reach a receiver whose request
schema is `extra="forbid"` (the engine's `RegisterWorkflowNodeRequest`)
cannot ship as a top-level payload key — every registration would 422 until
the receiver widens its schema, and the SDK releases before the engine does.

Pattern (#110, `contract` field):

1. Ship the field on the MANIFEST (top-level, omit-when-None — legacy
   serialization stays byte-identical).
2. Cross the wire INSIDE an existing declared free-form dict
   (`constraints["contract"]`), caller-supplied values winning on collision.
3. The receiver reads it from the dict (engine #658) and promotes it to a
   top-level field in ITS own widening release — the receiver owns its wire.

Test pins both directions: key present when declared, absent when not, and
never at the payload top level. Related: `manifest-field-three-producer-rule`
(the three producers are where the omission/re-add rules live).
