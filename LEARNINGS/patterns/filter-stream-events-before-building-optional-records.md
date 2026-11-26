# Filter stream events before building optional records

Scope: project | Confidence: 0.9 | Evidence: #293, `test_unrequested_drawing_is_not_materialized`
When selecting a subset of large JSON records with `ijson`, filter by map key before `kvitems` builds values. Testing only the returned keys misses allocations for unrequested drawings.
