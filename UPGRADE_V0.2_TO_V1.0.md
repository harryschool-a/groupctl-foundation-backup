# Upgrade from groupctl v0.2 to v1.0

This is an overlay patch for the existing v0.2 Git repository. It preserves `.git/`, your existing `.group/` event history, local member configuration, and unrelated files. It replaces the application and test files listed in the patch and adds the v1.0 agent/task/dashboard documentation and examples.

## 1. Confirm the repository and branch

Open PowerShell in the directory containing `groupctl.py`. The user in this project already created the branch `release/groupctl-v1.0`; do not create it again.

```powershell
git status
git branch --show-current
```

Continue only when the working tree is clean and the current branch is the intended v1.0 upgrade branch.

## 2. Extract the patch into the repository root

Download `groupctl_foundation_v1.0_upgrade_patch.zip`. With PowerShell still in the repository root, run (adjust the ZIP path if your browser saved it elsewhere):

```powershell
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\groupctl_foundation_v1.0_upgrade_patch.zip" -DestinationPath . -Force
```

The archive entries are rooted at the repository root. `-Force` replaces matching application/documentation/test files; it does not delete `.git/` or your existing `.group/` folder. Do not extract the standalone full-project ZIP over this repository.

## 3. Verify the upgrade

Run each command separately:

```powershell
python groupctl.py --version
python -m py_compile groupctl.py scripts/mock_agent.py tests/test_groupctl.py tests/test_v1_features.py
python -m unittest discover -s tests -v
python groupctl.py validate
python groupctl.py status
```

The version command should print `groupctl 1.0.0`. The existing historical G-12 events may still show review/integration limitations; the upgrade does not rewrite or auto-approve them.

## 4. Try the provider-neutral agent bridge

First generate a context bundle and a draft submission without recording an event:

```powershell
python scripts/mock_agent.py --person-id P17
```

Inspect `.group/local/mock_agent_context.json` and `.group/local/mock_agent_submission.json`. To explicitly submit the mock finding as a local event:

```powershell
python scripts/mock_agent.py --person-id P17 --submit
python groupctl.py validate
python groupctl.py status
```

This mock does not call an LLM or paid API. It demonstrates the JSON interface an external coding agent can consume.

## 5. Try the v1.0 coordination features

```powershell
python groupctl.py tasks
python groupctl.py audit
python groupctl.py dashboard --output .group/local/dashboard.html
```

The audit command can report attention-required historical work; that is a diagnostic, not automatic data repair. The dashboard is a local HTML report.

## 6. Run the three-member simulation

```powershell
python scripts/run_three_member_demo.py --auto-confirm-final
```

The demo uses temporary local Git repositories and a temporary bare remote. It does not use GitHub, additional people, or an AI API, and the temporary demo repositories are removed when the script exits.

## 7. Review and commit the upgrade

```powershell
git diff --check
git status
```

Inspect the diff. In particular, keep `.group/local/` artifacts out of the commit except `.group/local/.gitkeep`. Then stage and commit the reviewed v1.0 files:

```powershell
git add AGENT_INSTRUCTIONS.md CHANGELOG.md FINAL_VALIDATION.md PACKAGE_REVIEW_NOTES.md QUICKSTART_WINDOWS.md README.md VERSION groupctl.py scripts/mock_agent.py specifications/08_ai_agent_bridge.md examples/agent_finding_submission.json examples/agent_prompt_template.md tests/test_groupctl.py tests/test_v1_features.py UPGRADE_V0.2_TO_V1.0.md
git commit -m "feat: release groupctl v1.0 collaboration platform"
```

Do not push automatically. Review the resulting commit and follow your group's normal remote/PR process.

## Scope and limitations

v1.0 provides a local Git-backed collaboration CLI, structured tasks/events, an external-AI JSON bridge, a deterministic mock agent, a local dashboard, audit checks, and a repeatable three-member simulation. It is not a hosted service, does not authenticate member identities, and does not contain an autonomous LLM runtime. Human review remains required for semantic decisions, merges, and finalization.
