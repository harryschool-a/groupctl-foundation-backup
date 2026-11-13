# Upgrade groupctl v1.0 to v1.1 (Windows)

This upgrade patch is intended for a clean v1.0 working tree. It preserves `.git/` and the existing `.group/` event history.

## 1. Create a branch and check the working tree

```cmd
git status
git switch -c release/groupctl-v1.1
```

If the branch already exists, use `git switch release/groupctl-v1.1` instead. Do not proceed with unrelated uncommitted changes.

## 2. Extract the upgrade patch

Extract `groupctl_foundation_v1.1_upgrade_patch.zip` into the repository root, replacing matching application/documentation files. The archive has repository-relative paths. Do not extract the complete standalone archive over an existing Git repository.

CMD users can run:

```cmd
powershell -NoProfile -Command "Expand-Archive -LiteralPath '%USERPROFILE%\\Downloads\\groupctl_foundation_v1.1_upgrade_patch.zip' -DestinationPath '.' -Force"
```

## 3. Verify the upgrade

```cmd
python groupctl.py --version
python -m unittest discover -s tests -v
python groupctl.py validate
python groupctl.py --help
```

Expected version: `groupctl 1.1.0`. The package test suite currently contains 62 tests. The three-member demo adds three demo-only tests to its temporary project and records 65 passing tests on its canonical demo commit.

## 4. Configure live agents

Create tasks for the existing member P17:

```cmd
python groupctl.py task-create --task-id T-IMPLEMENT-A --title "Implement feature A" --assignee-id P17 --person-id P17
python groupctl.py task-create --task-id T-IMPLEMENT-B --title "Implement feature B" --assignee-id P17 --person-id P17
```

Copy the sample agent config:

```cmd
copy examples\\agents.example.json .group\\agents.json
notepad .group\\agents.json
```

Replace the model placeholder with a model name available from your OpenAI-compatible endpoint. The sample assumes a local endpoint at `http://localhost:11434/v1`. The local model server must already be running. For a hosted provider, use its HTTPS compatible endpoint and set `api_key_env` to an environment-variable name; never put the key itself in JSON.

Run two agents concurrently. The example creates two competing code proposals from the same starting commit; review both and select one for this working tree. Separate implementation worktrees are not automatically created by v1.1:

```cmd
python groupctl.py agents-run --config-file .group/agents.json --max-workers 2
```

## 5. Review and apply proposals

Each implementer returns a `.group/proposals/PR-....patch` file and a `code_proposal` event. Inspect the patch and event. Do not apply patches on `main`.

```cmd
git switch -c people/P17/agent-proposal-work
python groupctl.py agent-apply --proposal-id PR-REPLACE_ME --person-id P17 --expected-head FULL_BASE_COMMIT --human-approved
```

The command applies only to the working tree. It does not stage or commit. Inspect `git diff`, run tests, and commit the change yourself.

Publish the committed code contribution:

```cmd
python groupctl.py agent-publish --person-id P17 --agent-id coder-alpha --summary "Implement feature A" --test-run "python -m unittest discover -s tests -v"
```

Use another configured task and a different `agent_id` with `--role reviewer --change-id C-...` to obtain an AI review. A distinct AI reviewer operating under P17 is not the same as an independent human member.

## 6. Commit the v1.1 release

```cmd
git diff --check
git status
git add .
git diff --cached --check
git commit -m "Release groupctl v1.1 live agent runtime"
```

Do not push until a Git remote is intentionally configured and verified. This local project currently has no remote configured.
