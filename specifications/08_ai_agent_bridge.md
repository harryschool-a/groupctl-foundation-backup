# AI Agent Bridge — Version 0.3

## Purpose

Version 0.3 adds a provider-neutral boundary between `groupctl` and an external AI coding agent. The bridge uses JSON on disk/stdout so an agent can be supplied by a local coding assistant, a hosted model, or a deterministic mock without changing the collaboration protocol.

The bridge has two operations:

1. `agent-context` exports validated project context for a configured member.
2. `agent-submit` accepts one structured agent response, applies protocol checks, and writes one immutable event.

The bridge does not call a model API, execute generated code, commit, push, merge, or finalize a group.

## Context contract

Run:

```powershell
python groupctl.py agent-context --person-id P17
```

The command writes a JSON object to stdout. To save a local context bundle:

```powershell
python groupctl.py agent-context --person-id P17 --output .group/local/agent_context.json
```

To include events from fetched remote-tracking branches, fetch first and specify the remote:

```powershell
git fetch --all --tags --prune
python groupctl.py agent-context --person-id P17 --remote origin --output .group/local/agent_context.json
```

The context object contains:

- `schema_version`, `tool_version`, and `protocol_version`;
- group identity, canonical branch, assignment path and full assignment text;
- the configured member descriptor;
- repository branch, commit, working-tree cleanliness, changed paths and canonical-branch relationship when Git is available;
- recent validated event summaries;
- the supported submission event types;
- portable agent instructions and explicit safety rules.

`--limit` controls the number of recent event summaries (1–500; default 30). `--no-instructions` omits the contents of `AGENT_INSTRUCTIONS.md` from the context object. Context generation is read-only; it does not fetch, checkpoint events, stage files, or alter Git state.

## Submission contract

An external agent writes one JSON object with this shape:

```json
{
  "event_type": "finding",
  "payload": {
    "summary": "A concise engineering finding.",
    "evidence": ["A reproducible observation."]
  },
  "related_events": []
}
```

Submit it with an explicit member identity:

```powershell
python groupctl.py agent-submit --person-id P17 --input-file .group/local/agent_submission.json
```

The bridge currently accepts `change_published`, `finding`, `question`, `answer`, `review`, `test_result`, `integration_result`, `blocker`, and `synthesis_candidate`. It does not accept `final_candidate` or `final_result`; finalization remains a separate human-confirmed workflow.

Additional checks include:

- `review` must target a known published change and cannot be a self-review;
- `answer` must target a known question;
- a blocker naming a change must refer to a known published change;
- `change_published` must reference a commit and branch available in the local or fetched Git refs;
- `test_result` must reference a Git commit available in the repository;
- a successful `integration_result` must reference a merge commit that is an ancestor of its target branch;
- synthesis source change IDs must be known; their source event IDs are added to `related_events` automatically;
- all payloads still pass the existing event schema validator and cannot override the common event envelope.

The result is a local event only. A human or agent acting under explicit repository policy must inspect the generated file, then decide whether to commit and push it.

## Example mock agent

The repository includes a deterministic example that requires no provider account or API key:

```powershell
python scripts/mock_agent.py --person-id P17
```

This writes a context bundle and a sample finding submission under `.group/local/`, but it does not create an event. Inspect the draft and then run:

```powershell
python scripts/mock_agent.py --person-id P17 --submit
```

The mock then calls `agent-submit` and creates a validated local `finding` event. The mock is only a bridge smoke test; it does not demonstrate the reasoning quality of an LLM.

## Safety model and limitations

- The member ID is supplied explicitly by the caller; this is attribution metadata, not cryptographic authentication.
- Any local process with write access to the repository can invoke the bridge. GitHub permissions and server-side authorization remain external responsibilities.
- The bridge validates event shape and selected relationships; it does not prove that an AI's summary, review, test claim, or semantic judgement is true.
- The bridge deliberately does not automate commits, pushes, merges, code execution, or finalization.
- Fetched remote events are read-only inputs. Run `git fetch` yourself before requesting `--remote` context.

The JSON context/submission boundary is the stable adapter contract for future provider-specific integrations.
