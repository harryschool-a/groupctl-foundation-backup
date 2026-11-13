# groupctl v1.1 — Live Agent Quick Start (Windows)

## 1. Confirm v1.1

```cmd
python groupctl.py --version
python -m unittest discover -s tests -v
```

## 2. Prepare a personal work branch

Do not run implementer agents on `main`.

```cmd
git switch -c people/P17/live-agent-work
```

If the branch already exists, switch to it rather than creating it again:

```cmd
git switch people/P17/live-agent-work
```

## 3. Create two tasks

```cmd
python groupctl.py task-create --task-id T-IMPLEMENT-A --title "Implement feature A" --assignee-id P17 --person-id P17
python groupctl.py task-create --task-id T-IMPLEMENT-B --title "Implement feature B" --assignee-id P17 --person-id P17
```

Use different task IDs. Do not assign overlapping files unless you deliberately want to compare alternatives. v1.1 rejects duplicate task IDs in a concurrent config. Each agent claims its task as `in_progress`; another agent cannot take over that claim unless a human reopens/reassigns the task.

## 4. Configure the local provider

The easiest no-hosted-API path is a local service that exposes the OpenAI-compatible Chat Completions endpoint. For example, a local Ollama server commonly exposes:

```text
http://localhost:11434/v1
```

Make sure your local model service is running and you know its installed model name. No API key is required if your local endpoint does not require one.

Copy and edit the sample configuration:

```cmd
copy examples\agents.example.json .group\agents.json
notepad .group\agents.json
```

Replace `REPLACE_WITH_YOUR_INSTALLED_MODEL` with the exact model name available on your machine. Keep unique `agent_id` values. `person_id` must identify a real member descriptor; this starter project has P17.

If using a hosted OpenAI-compatible service, use its HTTPS base URL and set `api_key_env` to an environment variable name, not the key itself. For a current CMD session:

```cmd
set MY_AI_API_KEY=YOUR_KEY
```

## 5. Run two agents concurrently

```cmd
python groupctl.py agents-run --config-file .group/agents.json --max-workers 2
```

Each agent creates a structured proposal or finding event. An open task changes to `in_progress` when the agent starts and remains there until a human updates it. Implementer proposals are saved under `.group/proposals/`. They are not applied automatically. If two implementers run concurrently, their proposals are alternatives against the same starting commit. Choose one for this worktree; applying it makes other proposals from that base stale. v1.1 does not yet manage separate Git worktrees for multiple simultaneous implementation branches.

## 6. Inspect and apply one proposal

Inspect the proposal file and metadata. Record the proposal ID and base commit from its event. Make sure you are on a personal feature branch and the working tree has no unrelated code changes.

```cmd
git status
python groupctl.py agent-apply --proposal-id PR-REPLACE_ME --person-id P17 --expected-head FULL_BASE_COMMIT --human-approved
```

The `--human-approved` flag is an explicit assertion that you inspected the patch. Applying a proposal only changes files in your working tree; it does not stage or commit them.

## 7. Test, commit, and publish

Run the test commands stated by the proposal and any additional project tests. Inspect `git diff`. Then commit the accepted code yourself:

```cmd
git diff --check
git diff
git add path\to\changed\files
git commit -m "Implement feature from agent proposal"
```

Publish the committed contribution with the agent identity that produced it:

```cmd
python groupctl.py agent-publish --person-id P17 --agent-id coder-alpha --summary "Implement feature A" --test-run "python -m unittest discover -s tests -v"
```

## 8. Ask a second agent to review

Create a review task:

```cmd
python groupctl.py task-create --task-id T-REVIEW-A --title "Review feature A" --assignee-id P17 --person-id P17
```

Run a different agent identity (replace `C-...` with the change ID printed by `agent-publish`):

```cmd
python groupctl.py agent-run --person-id P17 --agent-id reviewer-beta --task-id T-REVIEW-A --role reviewer --change-id C-... --base-url http://localhost:11434/v1 --model YOUR_LOCAL_MODEL
```

The review is attributed to a distinct AI agent, but both agents still belong to the same human member. It is not a substitute for independent human review. After checking the task deliverable, the human can update its state:

```cmd
python groupctl.py task-create --task-id T-IMPLEMENT-A --title "Implement feature A" --assignee-id P17 --status completed --person-id P17
```

## Important

A live agent run requires an available OpenAI-compatible model endpoint. Local inference avoids API billing but still uses your computer's CPU/GPU and memory. Hosted providers may charge for usage. v1.1 does not install or start a model server for you.
