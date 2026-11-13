# groupctl 1.0

`groupctl` is a lightweight, file-backed collaboration layer for software teams in which humans and AI assistants work in parallel. Git remains the source of truth for code history; groupctl records collaboration intent, review evidence, task coordination, synthesis proposals, testing, and human-controlled finalization.

## What v1.0 includes

- Git-aware collaboration event validation and immutable event records.
- Local and remote event discovery.
- Provider-neutral AI Agent Bridge (`agent-context`, `agent-submit`).
- Structured task coordination (`task-create`, `tasks`).
- Safe synchronization (`sync`) that fetches before inspecting remote collaboration events.
- Status and protocol audit (`status`, `audit`).
- Local HTML collaboration dashboard (`dashboard`).
- Structured reviews, blockers, test evidence, integration results, and synthesis candidates.
- Human-confirmed finalization.
- A no-API mock agent and a three-member Git simulation.

## Safety model

An AI agent can contribute evidence and proposals, but groupctl does not give an agent unilateral authority to silently merge code, rewrite collaboration history, or finalize a release. Finalization remains explicitly human-confirmed.

## Quick start

```powershell
python -m unittest discover -s tests -v
python groupctl.py validate
python groupctl.py status
python groupctl.py tasks
python groupctl.py dashboard --output .group/local/dashboard.html
python scripts/mock_agent.py --person-id P17
python scripts/run_three_member_demo.py --auto-confirm-final
```

## Typical workflow

```text
SYNC → TASK → CONTEXT → WORK → PUB → REV → INT → TEST → SYNTHESIZE → AUDIT → FINAL
```

`SYNC`, `PUB`, `REV`, `INT`, `TEST`, `STATUS`, and `FINAL` are collaboration procedures. The CLI provides deterministic validation and record-keeping around them.

## Important limitation

v1.0 is a collaboration foundation, not a hosted SaaS service or a built-in LLM. It intentionally remains provider-neutral: external AI tools can consume `agent-context` and return structured data through `agent-submit`.
