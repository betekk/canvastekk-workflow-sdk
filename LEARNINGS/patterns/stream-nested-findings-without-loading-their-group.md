# Pattern: Stream nested findings without loading the parent group

**Scope:** project · **Confidence:** high · **Evidence:** `python/tests/test_check_result_reader.py` (#3521)
When a nested check can carry thousands of drawings, parse its descriptor without measurement events and read rows in a separate stream. Preserve the original group and row indices, even when the check key follows the measurements.
