"""Deprecated alias module — renamed to canvastekk_workflow_sdk.node_output_uploads.

ADR 0001 (explicit node naming, #271): every old module path keeps working
and warns as deprecated; removed in 1.0.0 (#272).
"""

from __future__ import annotations

import warnings

_deprecated_alias_of = "canvastekk_workflow_sdk.node_output_uploads"

warnings.warn(
    "canvastekk_workflow_sdk.uploads is deprecated; import"
    " canvastekk_workflow_sdk.node_output_uploads instead (ADR 0001; removal in 1.0.0).",
    DeprecationWarning,
    stacklevel=2,
)

from canvastekk_workflow_sdk.node_output_uploads import *  # noqa: E402, F401, F403
from canvastekk_workflow_sdk.node_output_uploads import (  # noqa: E402
    NodeOutputS3PresignedUploader,
    NodeOutputUploader,
    NodeOutputUploadSession,
    NodeOutputUploadTarget,
    get_default_node_output_uploader,
)

# Deprecated public names (ADR 0001, #271) — old name -> renamed symbol.
OutputUploader = NodeOutputUploader  # deprecated name (ADR 0001, #271)
S3PresignedUploader = NodeOutputS3PresignedUploader  # deprecated name (ADR 0001, #271)
UploadSession = NodeOutputUploadSession  # deprecated name (ADR 0001, #271)
UploadTarget = NodeOutputUploadTarget  # deprecated name (ADR 0001, #271)
get_default_uploader = get_default_node_output_uploader  # deprecated name (ADR 0001, #271)
