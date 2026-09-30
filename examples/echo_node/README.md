# Echo Node

Minimal example showing file input/output with the CanvasTEKK Workflow SDK.

## What it demonstrates

- **File fields**: `format: "file"` with `x-accept` and `x-maxSizeBytes` extensions
- **Auto-download**: SDK automatically downloads presigned URL file inputs before execute()
- **Runtime validation**: SDK auto-validates downloaded files against `x-accept` and `x-maxSizeBytes`
- **Output upload**: Returns a local path; SDK uploads via the engine's multipart upload session
- **CLI validation**: Offline manifest validation during development

## Setup

```bash
cd examples/echo_node/
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e "../../../python/"  # install SDK from local source
```

## Validate the manifest

```bash
# Human-readable
python -m canvastekk_workflow_sdk validate handler:definition

# JSON for CI
python -m canvastekk_workflow_sdk validate handler:definition --json
```

## Run locally

```bash
uvicorn handler:app --reload --port 8001
```

## Test with curl

```bash
# Health check
curl http://localhost:8001/health

# Manifest
curl http://localhost:8001/manifest

# Execute (simulates an engine sending a multipart upload session)
curl -X POST http://localhost:8001/execute \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": "run-test-1",
    "node_id": "echo-1",
    "inputs": {
      "input_file": "https://example.com/test.txt"
    },
    "output_upload_url": {
      "output_file": {
        "kind": "multipart-upload-session",
        "session_token": "tok-1",
        "initiate_url": "https://engine.example/sessions/tok-1/initiate",
        "complete_url": "https://engine.example/sessions/tok-1/complete",
        "abort_url": "https://engine.example/sessions/tok-1/abort",
        "status_url": "https://engine.example/sessions/tok-1/status"
      }
    }
  }'
```

## Run tests

```bash
pip install pytest httpx
pytest tests/
```

## Docker build

```bash
docker build -t echo-node .
docker run -p 8001:8001 echo-node
```
