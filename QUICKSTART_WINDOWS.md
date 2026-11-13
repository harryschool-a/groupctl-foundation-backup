# Windows Quick Start — groupctl v0.2

## 1. Extract safely

Extract this ZIP into a **new folder** (for example, `Downloads\groupctl_foundation_v0.2`). Do not extract it over an existing working repository. The archive is a tested package snapshot, not a patch that knows how to merge your local uncommitted work.

This ZIP does not include `.git` history, remote configuration, or credentials. To contribute to your existing GitHub project, use the separate **upgrade patch** on a new branch based on your current collaboration branch; do not try to push directly from this extracted snapshot.

Open PowerShell in the extracted folder, the one containing `groupctl.py`.

## 2. Check the tools

```powershell
python --version
git --version
```

Python 3.10+ and Git for Windows are recommended. There are no third-party Python packages to install.

## 3. Run the checks

```powershell
python -m unittest discover -s tests -v
python groupctl.py validate
python groupctl.py status
```

The packaged repository is already initialized as group `G-12`. Do not run `init` in this package.

## 4. Run the three-member simulation

Interactive demonstration (asks before simulated finalization):

```powershell
python scripts/run_three_member_demo.py
```

Fully scripted demonstration (simulates the final confirmation):

```powershell
python scripts/run_three_member_demo.py --auto-confirm-final
```

The demo creates a temporary bare Git remote and three temporary clones on your computer. It does not use GitHub, does not need other people, does not call an AI API, and does not modify the extracted project folder. It is a test of the protocol and Git workflow, not proof of live multi-user operation.

## 5. Useful commands

```powershell
# Validate group configuration, events, members, and final records
python groupctl.py validate

# List local collaboration events
python groupctl.py events

# Summarize local group status
python groupctl.py status

# After fetching, include events on fetched origin branches
git fetch --all --tags --prune
python groupctl.py status --remote origin

# Inspect new remote events (does not merge them)
python groupctl.py remote-events --remote origin --new-only
```

## 6. Use the AI collaboration procedures

Open `AGENT_INSTRUCTIONS.md` in the context of the coding assistant you use with this repository. The prompt commands are procedures for that assistant, not all shell commands:

- `SYNC` — discover and inspect work from the group.
- `PUB` — publish your own coherent contribution.
- `REV C-...` — review one contribution without merging it.
- `INT C-...` — integrate a specific reviewed contribution and verify it.
- `TEST` — run checks and publish exact-commit test evidence.
- `STATUS` — explain the current group position.
- `SYNTHESIZE <topic>` — compare contributions and record a traceable synthesis proposal.
- `FINAL` — prepare a final candidate; finalization still requires explicit human confirmation.

A synthesis candidate is not a code merge. It records source changes, proposed approach, alternatives, tradeoffs, validation plan, decision, and unresolved concerns. The resulting implementation must still be separately published, reviewed, tested, and integrated.

## 7. Important limitations

This release provides a local CLI, shared Git event protocol, portable AI-agent instructions, finalization checks, and a simulated multi-member workflow. It does **not** provide an autonomous AI-agent runner, centralized server, secure identity/authorization system, task scheduler, or automatic semantic judge. Real participants still need access to the same Git repository and must inspect diffs and evidence.
