# An integral float breaks byte parity between the Python and TypeScript writers

Python's `json.dumps(5.0)` writes `5.0`; JavaScript's `JSON.stringify(5)`
writes `5` (JS has no float/int distinction). A shared golden containing an
integral float can never be reproduced by both writers (#283: the 1.1.0
golden's `"tolerance": 5.0` failed in TypeScript).

Fix at the source, not in the golden: keep numbers in the type the input
gave (`check_verdict.rules_from_inputs` no longer forces `float(value)`), and
keep integral floats out of shared goldens. Non-integral floats (`1.25`) are
written identically by both runtimes.
