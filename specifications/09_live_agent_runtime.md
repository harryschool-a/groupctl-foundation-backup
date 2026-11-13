# Live AI Agent Runtime — Version 1.1

## Purpose

Version 1.1 adds a live provider-backed runtime. Agents can receive a task and bounded repository context, call an OpenAI-compatible Chat Completions endpoint, and return structured findings, reviews, or code proposals. Multiple configured agents can run concurrently.

The runtime supports local endpoints such as an Ollama OpenAI-compatible server and hosted endpoints that implement the same API shape. Hosted credentials are read from environment variables and are never stored in `.group/agents.json`.

## Commands

### One agent

```powershell
python groupctl.py agent-run --person-id P17 --agent-id coder-alpha --task-id T-01 --role implementer --base-url http://localhost:11434/v1 --model YOUR_LOCAL_MODEL
```

Roles:

- `implementer`: requests a Git unified-diff code proposal;
- `reviewer`: requires `--change-id` and returns a structured review;
- `analyst`: returns a structured finding.

Every run requires a task whose latest `task_assigned` record is `open` or `in_progress` and assigned to the supplied `person_id`. If the task is `open`, the runtime appends an `in_progress` task event when the agent starts, attributed to that `agent_id`. A task already claimed by a different agent cannot be started by a second agent. A failed run remains `in_progress` for the same agent to resume or for a human to reopen/reassign. The task remains in progress until a human records its next state. A human can reopen it for another agent or mark it completed after verifying the deliverable, for example with `task-create --task-id T-01 --title "Implement feature" --assignee-id P17 --status completed --person-id P17`.

### Concurrent agents

Copy `examples/agents.example.json` to `.group/agents.json`, edit the model, endpoint, identity, and task IDs, create the referenced tasks, then run:

```powershell
python groupctl.py agents-run --config-file .group/agents.json --max-workers 2
```

The configuration supports one to eight agents. The runtime runs up to the requested worker count. Each agent must have a unique `agent_id` and a distinct `task_id`; duplicate task IDs are rejected to prevent concurrent claims. Several agents may be operated by the same human `person_id`; their events retain both the human sponsor and the distinct agent identity.

Concurrent implementer agents produce competing patch artifacts against the same starting HEAD; they do not write into the working tree. The human should inspect and select a proposal. Applying one proposal changes the current branch, so other proposals from the old base become stale and must be regenerated. v1.1 does not yet provision separate Git worktrees for parallel implementation branches.

### Apply a code proposal

An implementer does not write into the worktree. It creates an immutable patch artifact under `.group/proposals/` and a `code_proposal` event containing the base commit and SHA-256 digest.

Review the patch first. Then switch to a personal feature branch based on the exact proposal base commit and run:

```powershell
python groupctl.py agent-apply --proposal-id PR-... --person-id P17 --expected-head FULL_BASE_COMMIT --human-approved
```

The command refuses to apply when:

- human approval is absent;
- the current branch is the canonical branch;
- HEAD differs from the proposal base commit;
- unrelated working-tree changes exist;
- the patch digest differs from its event;
- Git's `apply --check` rejects the patch.

It applies changes to the worktree only. It does not stage, commit, test, push, or merge. The human must inspect the diff and run tests.

### Publish and review

After a human has inspected, tested, and committed the accepted patch on the feature branch, publish the contribution:

```powershell
python groupctl.py agent-publish --person-id P17 --agent-id coder-alpha --summary "Implement the assigned feature" --test-run "python -m unittest discover -s tests -v"
```

A second agent can review it:

```powershell
python groupctl.py agent-run --person-id P17 --agent-id reviewer-beta --task-id T-REVIEW --role reviewer --change-id C-... --base-url http://localhost:11434/v1 --model YOUR_LOCAL_MODEL
```

A different `agent_id` under the same `person_id` is recorded as a distinct-agent review. It is not represented as an independent human member review; human reviewers remain valuable for higher assurance.

## Provider interface

The runtime sends a standard JSON request to `<base_url>/chat/completions` with `model`, `messages`, `temperature`, and `max_tokens`. It expects the assistant message content to be one JSON object.

- Base URLs must be HTTPS except for localhost/loopback endpoints.
- API keys are loaded from the named environment variable (`api_key_env` or `--api-key-env`).
- No key is required for a local endpoint that does not use authentication.
- Provider calls have a bounded timeout and an 8 MiB response limit.
- The runtime does not use shell interpolation or execute model output.

## Code proposal response

Implementers return:

```json
{
  "event_type": "code_proposal",
  "payload": {
    "summary": "Implement the requested feature.",
    "patch": "diff --git a/example.py b/example.py\\n...",
    "files_changed": ["example.py"],
    "test_plan": ["python -m unittest discover -s tests -v"],
    "risk_level": "low"
  },
  "related_events": []
}
```

The runtime stores `patch` separately and creates a structured event with proposal ID, task ID, base commit, patch path, digest, file list, test plan, and risk level. Paths under `.git`, `.group`, traversal paths, environment files, and secret-like path components are rejected. Both `diff --git` paths and `---`/`+++` file-header paths are checked.

## Event identity and review policy

Events may contain optional top-level `agent_id`. `person_id` remains the configured human member who owns or supervises the local agent. Distinct `agent_id` values allow the audit to recognize separate AI agents working for one member. This metadata is attribution, not cryptographic authentication.

A review is rejected as self-review when the same human/member identity submits it and the same agent identity authored the change. If the change has no `agent_id`, a different human member is still required.

## Safety boundaries

- Model output is untrusted data. It is parsed as JSON and validated before an event is written.
- Implementer models create patch files only; the model never applies them automatically.
- `agent-apply` requires a human confirmation flag and never operates on the canonical branch.
- Applied code remains uncommitted and must be inspected and tested by the human.
- No agent can commit, push, merge, or finalize through this runtime.
- API keys are never written to event files, logs, or agent config.
- A provider response is not proof that its claims are correct.

## Limitations

This is a local runtime, not a multi-tenant server. Agent identity is an attribution label supplied by the local operator. Agents share the configured local model endpoint or use different compatible endpoints. Live Git hosting authentication and remote multi-user authorization remain Git/provider responsibilities.
