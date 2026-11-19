"""Deprecated alias module — renamed to canvastekk_workflow_sdk.cds_multipart_upload.

ADR 0001 (explicit node naming, #271): every old module path keeps working
and warns as deprecated; removed in 1.0.0 (#272).
"""

from __future__ import annotations

import warnings

_deprecated_alias_of = "canvastekk_workflow_sdk.cds_multipart_upload"

warnings.warn(
    "canvastekk_workflow_sdk.multipart is deprecated; import"
    " canvastekk_workflow_sdk.cds_multipart_upload instead (ADR 0001; removal in 1.0.0).",
    DeprecationWarning,
    stacklevel=2,
)

from canvastekk_workflow_sdk.cds_multipart_upload import *  # noqa: E402, F401, F403
from canvastekk_workflow_sdk.cds_multipart_upload import (  # noqa: E402
    upload_via_cds_multipart_session,
)

# Deprecated public names (ADR 0001, #271) — old name -> renamed symbol.
upload_via_session = upload_via_cds_multipart_session  # deprecated name (ADR 0001, #271)
