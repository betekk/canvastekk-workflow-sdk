# Dual Descriptor Contracts: Derive Control Extras Once, Mask on Legacy

**Category**: pattern
**File**: `patterns/dual-descriptor-contract-derive-extras-once.md`
**Summary**: When one client must speak two descriptor contracts selected by a discriminator, make the discriminator decision once at the client boundary and derive every downstream wire extra from it. For upload descriptors (#196): `is_capability = kind == multipart-upload-capability` yields `control_element = element if is_capability else None`, so legacy complete/abort/status cannot accidentally gain capability fields, and capability status sets only its named query keys (`upload_id`, `index`, `suffix`) — never `dict.update(element)` or a spread of unchecked object fields. Mirror the same matrix in raw-wire tests parameterized over both kinds, asserting exact JSON bodies and query strings per contract; schema-level parse tests alone miss field leakage at the transport layer.
**Date**: 2026-10-26
