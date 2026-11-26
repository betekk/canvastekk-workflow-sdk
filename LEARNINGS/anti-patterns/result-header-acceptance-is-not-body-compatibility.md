# Result header acceptance is not body compatibility

Scope: project | Confidence: 0.9 | Evidence: #293, `python/tests/test_check_result_reader.py`
When adding a body version, replay both the header projection and the grouped finding reader with the published SDK. A quick verdict can succeed even when a finding reader rejects the same saved run.
