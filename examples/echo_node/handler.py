"""
Echo Node — minimal example of file I/O with the CanvasTEKK Workflow SDK.

Demonstrates:
  - File input/output with format: "file" and x-* extensions
  - Downloading from presigned URLs with httpx
  - Runtime validation with validate_file_input()
  - Writing output files via context.output_path()
  - CLI manifest validation: python -m canvastekk_workflow_sdk validate handler:manifest
"""

from pathlib import Path

from canvastekk_workflow_sdk import NodeExecutionContext, WorkflowNodeBase, WorkflowNodeManifest

manifest = WorkflowNodeManifest(
    slug="echo",
    version="1.0.0",  # semantic version — engine enforces immutability; bump for schema changes
    name="Echo",
    description="Receives a file, validates it, and writes it to output",
    input_schema={
        "type": "object",
        "properties": {
            "input_file": {
                "type": "string",
                "format": "file",
                "description": "Input file to echo",
                "x-accept": [".txt", ".csv", ".json"],
                "x-maxSizeBytes": 10485760,
            },
        },
        "required": ["input_file"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "output_file": {
                "type": "string",
                "format": "file",
                "description": "Echoed output file",
            },
        },
    },
    category="utility",
    timeout_seconds=60,
)


class EchoNode(WorkflowNodeBase):
    manifest = manifest

    def execute(self, inputs: dict, context: NodeExecutionContext) -> dict:
        # The SDK's auto-download pipeline has already fetched the file-input
        # URL and replaced the value with a LOCAL path — consume it directly
        # (the old manual httpx download double-downloaded and contradicted
        # the SDK contract).
        local_path = Path(inputs["input_file"])

        context.report_progress(0.5, "Validating input file")
        manifest.validate_file_input("input_file", local_path)

        context.report_progress(0.7, "Writing output")
        output_path = context.output_path("echo_output.txt")
        output_path.write_bytes(local_path.read_bytes())

        context.report_progress(1.0, "Done")
        return {"output_file": str(output_path)}


app = EchoNode().create_app()
