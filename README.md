# groupctl 1.1

`groupctl` is a local-first collaboration layer for software teams in which humans and AI agents work in parallel. Git remains the source of truth for code history; groupctl records collaboration intent, task coordination, reviews, test evidence, synthesis proposals, and human-controlled finalization.

## What v1.1 adds

- Live provider-backed agents using an OpenAI-compatible Chat Completions endpoint.
- Support for local model endpoints (including Ollama-compatible APIs) and HTTPS hosted endpoints.
- Concurrent execution of up to eight configured agents with unique agent identities.
- Task-bound implementer, reviewer, and analyst roles.
- Structured code proposals stored as Git patches with SHA-256 integrity records.
- Human-gated patch application on non-canonical branches, with exact base-commit checks.
- Agent-attributed findings, reviews, sessions, and published changes.
- Distinct-agent review attribution when multiple agents are operated by one group member.
- API keys read from environment variables, never stored in the agent config or events.

The v1.0 features remain: validated immutable events, remote discovery, task tracking, status/audit, HTML dashboard, synthesis candidates, and human-confirmed finalization.

## Quick start

```powershell
python --version
python -m unittest discover -s tests -v
python groupctl.py --version
python groupctl.py validate
python groupctl.py status
python groupctl.py dashboard --output .group/local/dashboard.html
```

See `QUICKSTART_V1.1_LIVE_AGENTS.md` for a Windows walkthrough and `specifications/09_live_agent_runtime.md` for the runtime contract. Copy `examples/agents.example.json` to `.group/agents.json` and configure your endpoint/model before using `agents-run`.

## Live agent workflow

```text
TASK → AGENT CONTEXT → LIVE MODEL → CODE PROPOSAL → HUMAN REVIEW
     → HUMAN-APPROVED PATCH APPLY → TEST → COMMIT → PUBLISH → SECOND-AGENT REVIEW
```

One agent can be run with `agent-run`; several agents can run concurrently with `agents-run` using distinct tasks. Implementers return patches as artifacts; they do not write code directly into the worktree. Concurrent implementers generate competing patches against the same starting commit; choose one proposal for the current worktree. v1.1 does not provision separate worktrees for parallel implementation branches. Humans inspect and apply an accepted patch using `agent-apply --human-approved`, then test and commit it themselves. `agent-publish` records the committed contribution and its agent identity. A distinct agent can then review it.

## Provider setup

The runtime calls `<base_url>/chat/completions`. A local OpenAI-compatible endpoint can use HTTP on localhost and does not need a key unless the service requires one. Non-local endpoints must use HTTPS. Hosted API keys are loaded from an environment variable named in the agent config; do not put the actual key in JSON, prompts, events, or Git.

Local inference avoids hosted API billing, but consumes local CPU/GPU memory and requires an installed/running model. Hosted providers may charge for requests. groupctl does not download, install, or start model servers.

## Safety model

- Agent identity is attribution metadata, not authentication. `person_id` identifies the responsible group member; `agent_id` distinguishes agents operated by that member.
- Model outputs are untrusted and must satisfy event and patch validation.
- An implementer creates a patch artifact; it cannot execute, apply, stage, commit, push, or merge it.
- `agent-apply` requires explicit human approval, a feature branch, a clean code worktree, and an unchanged base commit.
- Applied code remains uncommitted and must be inspected and tested by the human.
- AI review by a distinct agent is not equivalent to independent human review.
- No agent can finalize the group. Finalization requires explicit human confirmation.

## Limitations

v1.1 is a local runtime, not a hosted multi-tenant service. It does not provide authentication, access control across machines, remote worker provisioning, automatic model installation, or proof that model-generated code/reviews are correct. Git hosting permissions remain the responsibility of the Git provider.
