---
name: api-endpoint-owner-scope-hardening
description: Workflow command scaffold for api-endpoint-owner-scope-hardening in AGENTWHITE.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /api-endpoint-owner-scope-hardening

Use this workflow when working on **api-endpoint-owner-scope-hardening** in `AGENTWHITE`.

## Goal

Harden or scope API endpoints and related logic to enforce per-user or per-owner access controls.

## Common Files

- `routes/*_routes.py`
- `src/*`
- `tests/test_*owner_scope.py`
- `tests/test_*_gate.py`
- `tests/test_*_matching.py`
- `tests/test_*_fire_scope.py`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Update one or more routes/*_routes.py files to add or tighten owner checks.
- Update corresponding src/* files (e.g., src/task_scheduler.py, src/chat_handler.py) to propagate or enforce owner scoping.
- Add or update tests in tests/ to verify owner scoping and regression coverage.

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.