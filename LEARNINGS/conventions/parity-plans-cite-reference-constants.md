# Parity Plans Must Cite Reference Constants with file:line

**Category:** conventions · **Scope:** cross-SDK parity work · **Date:** 2026-09-29

## The rule

A plan claiming "matches <reference> exactly" must quote the reference's **actual constants with file:line**, and every deliberate divergence gets an explicit "diverges because" note. DA-3314's first draft claimed exact python parity while citing the *legacy single-PUT* backoffs (0.5/1s, `uploads.py:171`) for the *multipart* path (1.0/2.0s, `multipart.py:49`), and specified transient-only part retry where python's `_put_one_part` retries any error incl. 4xx (`multipart.py:163-178`). Without the citations, tests would have pinned wrong behavior as "parity" and misled anyone debugging slow or failing part uploads.

## Application

- Quote constants: retry counts, backoffs, timeouts (control-plane vs data-plane), parallelism, memory ceilings.
- Mark each divergence: "diverges because <reason>" (e.g. TS retries transient-only on legacy PUTs but mirrors python's retry-any on multipart parts).
