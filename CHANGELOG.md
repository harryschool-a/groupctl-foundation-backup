# Changelog

## 1.1.0 — Live AI-agent runtime

- Added an OpenAI-compatible live provider adapter, including local endpoints and environment-variable credentials.
- Added `agent-run` and concurrent `agents-run` for task-bound implementer, reviewer, and analyst agents.
- Added immutable `code_proposal` records and SHA-256-protected patch artifacts.
- Added human-gated `agent-apply`, requiring a feature branch, unchanged base commit, clean code worktree, and explicit approval.
- Added `agent-publish` for committed changes with agent attribution.
- Added distinct `agent_id` attribution and distinct-agent review checks while retaining human member identity.
- Added integration tests using a local fake OpenAI-compatible HTTP endpoint; no paid API is required for tests.
- Added microsecond event timestamps so rapid task-state transitions retain deterministic ordering while old timestamps remain compatible.
- Prevented duplicate task claims by configured agents and expanded patch validation to reject secret-like directory and file-header paths.

## Earlier releases

# Changelog

## 1.0.0

### Added
- Structured task records and task listing.
- Safe `sync` command for fetch + remote collaboration discovery.
- Local HTML dashboard generated from validated collaboration records.
- Collaboration audit for missing independent reviews and recorded blockers.

### Retained from v0.3
- Provider-neutral AI Agent Bridge.
- Mock agent workflow without paid APIs.
- Remote event validation, status, review, synthesis, test evidence, and human-confirmed finalization.

### Compatibility
- The collaboration protocol remains `0.1` so existing v0.x event and member records remain readable.
