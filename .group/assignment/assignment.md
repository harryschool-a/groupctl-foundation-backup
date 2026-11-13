# Group Assignment

**Group:** `G-12`  
**Protocol version:** `0.1`  
**Canonical branch:** `main`  
**Status:** Version 0.1 implementation and demonstration package

## 1. Project objective

Build the first working collaboration layer for a programming group in which several students each work with a local AI coding agent, while contributing to one shared software project through a shared Git repository.

The system must help the group discover, review, integrate, test, and finalize one another's work. It must not depend on private chat history as the only record of engineering decisions or changes.

The central design principle is:

> Git records source-code history. `groupctl` and the repository conventions add the shared collaboration context needed by humans and AI agents to work safely as one group.

## 2. Users and operating model

A group has two or more human members. Each member works with a local AI coding agent of their choice, such as Codex, Gemini, or another agent capable of using the local command line and Git.

Each member has:

- a stable `person_id` and the group's `group_id`;
- a local clone of the shared repository;
- a personal work branch, normally named `people/<person_id>/<topic>`;
- a local AI agent directed by the member;
- access to the group's committed assignment, source code, tests, and collaboration records.

The configured canonical branch, normally `main`, represents the group's accepted integrated state. A personal branch may contain experimental or unfinished work and must not be treated as accepted group work merely because it has been pushed.

## 3. Required product capabilities

The implementation must provide the following capabilities:

1. **Repository setup and identity** — initialize and validate the `.group/` collaboration structure, group configuration, and member descriptors.
2. **Structured collaboration events** — create, validate, and list immutable JSON events for published changes, findings, questions, answers, reviews, test results, integration results, blockers, and finalization.
3. **Remote event discovery** — inspect events available on fetched remote-tracking branches without silently changing the working branch or accepting the changes they describe.
4. **AI-agent procedures** — provide portable instructions that explain how an agent should interpret and execute the commands in Section 4.
5. **Safe Git collaboration** — keep personal work separate from the canonical branch, inspect actual diffs, handle conflicts deliberately, and verify integration rather than assuming that a successful Git merge proves correctness.
6. **Testing evidence** — run relevant checks after integration and publish enough evidence for other group members to understand what was tested and on which code state.
7. **Group finalization** — prepare a candidate report from the canonical accepted state and its evidence, then create final records only after explicit human confirmation.

## 4. Human-to-agent command vocabulary

The human-facing commands are concise prompts to the local AI agent. They are not necessarily shell subcommands.

| Command | Required meaning |
|---|---|
| `SYNC` | Fetch and inspect current group state and new collaboration events; explain what changed and what remains separate. |
| `PUB` | Check and publish a coherent contribution on the member's personal branch, then publish a `change_published` event. |
| `INT <change_id>` | Inspect a published change, integrate it according to repository policy, resolve or report conflicts, verify the result, and publish an integration result. |
| `REV <change_id>` | Inspect and assess a published change, report issues and evidence, and publish a review without silently integrating it. |
| `TEST` | Run appropriate checks against the intended code state and publish a structured test result. |
| `STATUS` | Report branch and commit state, local changes, canonical relationship, relevant events, test state, blockers, and a recommended next action. |
| `FINAL` | Review the canonical state and outstanding work, prepare a final candidate, obtain human confirmation, and only then publish finalization records. |

The detailed procedures in `specifications/05_command_procedures.md` and agent behavior rules in `specifications/06_agent_behavior_specification.md` are normative.

## 5. Shared repository records

The collaboration layer owns the `.group/` directory. At minimum it contains:

- `group.json` — protocol version, group identity, canonical branch, and assignment path;
- `assignment/assignment.md` — this group's actual project assignment;
- `members/<person_id>.json` — committed member descriptors;
- `events/<event_id>.json` — immutable, structured collaboration events;
- `final/` — candidate and confirmed finalization records;
- `local/` — local-only helper state, normally excluded from Git except for `.gitkeep`.

The event contract in `specifications/03_event_format_contract.md` defines the event envelope and event-specific fields. Published events must not be edited in place; corrections should be represented by new related events.

## 6. Safety and acceptance rules

The implementation and its agents must preserve these distinctions:

- Publishing a branch or event does not mean that a change has been reviewed.
- Discovering an event does not mean that its change is compatible with the current code.
- Reviewing a change does not integrate it.
- A successful Git merge does not prove that the combined program is correct.
- Passing tests is evidence for the tested code state, not proof that all requirements are satisfied.
- A final candidate is not a confirmed final result.
- Finalization requires explicit human confirmation and must not silently include unintegrated work.

Agents must inspect actual commits and diffs, protect other members' work, avoid destructive Git operations without authorization, and raise a blocker when a conflict or design uncertainty cannot be resolved safely.

## 7. Version 0.1 scope boundaries

Version 0.1 is a local collaboration helper layered on Git. It does not require:

- a Dispatcher or cross-group task allocation;
- automatic task planning;
- OpenAI, Gemini, or other vendor API integration;
- a dedicated server or custom network protocol;
- autonomous operation without a human directing the local agent;
- automatic grading or a graphical interface.

The design should remain AI-vendor-neutral and use the shared Git repository as its persistent collaboration substrate.

## 8. Required demonstration and completion criteria

A successful demonstration must use at least three simulated or real members with separate work branches and one shared canonical branch. It must demonstrate:

1. two independent changes being created and published;
2. one member discovering another member's published change through repository events;
3. review and/or integration based on inspection of the actual change;
4. at least one clean Git integration;
5. a deliberately conflicting change and a reasoned conflict resolution, or a blocker when safe resolution is not possible;
6. post-integration verification, including relevant automated tests;
7. publication of integration and test evidence;
8. an accepted canonical group state;
9. a final candidate based on that canonical state and its evidence;
10. explicit human confirmation before finalization records are created.

The group must also run the automated test suite and `groupctl validate`. A local simulation is acceptable for the Version 0.1 development demonstration, but it must be described honestly and must not be presented as proof of live GitHub permissions or independently operated AI-agent collaboration.

## 9. Deliverables

The repository submission must include:

- the `groupctl.py` command-line helper;
- `AGENT_INSTRUCTIONS.md` with the portable command procedures;
- the `.group/` repository structure and this completed assignment;
- the companion specifications under `specifications/`;
- automated tests under `tests/`;
- a repeatable multi-member demonstration under `scripts/`;
- usage and validation documentation in `README.md` and `FINAL_VALIDATION.md`;
- truthful final candidate and finalization records, when human confirmation has been obtained.

## 10. Governing specifications

This assignment is implemented in accordance with the following documents in `specifications/`:

- `00_group_collaboration_assignment.md` — original project brief and success demonstration;
- `01_architecture_and_workflow.md` — system components and workflow;
- `02_repository_contract.md` — repository layout and metadata;
- `03_event_format_contract.md` — event schema and immutability;
- `04_command_reference.md` — human-to-agent command meanings;
- `05_command_procedures.md` — required command procedures;
- `06_agent_behavior_specification.md` — agent safety and collaboration behavior;
- `07_testing_and_finalization.md` — validation and finalization requirements.

If this assignment is later replaced by a different project assigned to the group, update this file to that actual assignment while retaining the collaboration metadata and protocol contracts.
