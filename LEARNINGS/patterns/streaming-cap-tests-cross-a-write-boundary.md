# Streaming Cap Tests Cross a Write Boundary

**Date:** 2026-11-12 · **Source:** #248 code review (NOTE) · **Confidence:** high
**Scope:** tests for streamed downloads with declared and running byte caps

## Rule

Cover three distinct behaviors instead of treating any oversized body as sufficient:

- A declared over-cap `content-length` rejects before body iteration and closes the response.
- An undeclared body writes one in-cap chunk, overflows on a later chunk, closes the response, and removes the partial file.
- A successful streamed response also closes; redirect responses close before the next hop.

A single oversized first chunk proves rejection and unlinking, but never reaches the write-then-fail path that partial-file cleanup is meant to protect.

## Evidence

- `python/tests/test_file_download.py:800-855` (#248) separates pre-iteration rejection from a two-chunk running-cap failure and checks response exit plus cleanup.
- `python/canvastekk_workflow_sdk/base.py:289-360` scopes each streaming response and unlinks the local file from the write failure guard.
