#!/usr/bin/env python3
"""A deterministic, no-API example of the v1.0 external-agent bridge.

This is intentionally a mock, not an LLM. It demonstrates the JSON contract an
external AI coding agent can follow: request context, prepare a structured event,
and optionally ask groupctl to validate and record it.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_cli(project_root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(project_root / "groupctl.py"), *arguments]
    return subprocess.run(
        command,
        cwd=project_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Exercise the groupctl v1.0 agent bridge without an AI API.")
    parser.add_argument("--root", default=".", help="project root")
    parser.add_argument("--person-id", required=True, help="configured member ID")
    parser.add_argument("--summary", default="Mock agent inspected the current assignment and collaboration context.")
    parser.add_argument("--evidence", action="append", default=[], help="evidence line; may be repeated")
    parser.add_argument("--remote", help="include fetched remote events, e.g. origin")
    parser.add_argument("--submit", action="store_true", help="submit the draft as a local finding event")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    context_path = root / ".group" / "local" / "mock_agent_context.json"
    submission_path = root / ".group" / "local" / "mock_agent_submission.json"
    context_path.parent.mkdir(parents=True, exist_ok=True)

    context_command = ["agent-context", "--person-id", args.person_id, "--output", str(context_path)]
    if args.remote:
        context_command.extend(["--remote", args.remote])
    result = run_cli(root, *context_command)
    if result.returncode != 0:
        sys.stderr.write(result.stderr or result.stdout)
        return result.returncode

    try:
        context = json.loads(context_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not read generated agent context: {exc}", file=sys.stderr)
        return 1

    evidence = args.evidence or [
        f"The supplied context identifies group {context['group']['group_id']}.",
        f"The assignment is available at {context['assignment']['path']}.",
        f"The context contains {context['collaboration']['event_count']} validated collaboration event(s).",
    ]
    submission = {
        "event_type": "finding",
        "payload": {"summary": args.summary, "evidence": evidence},
        "related_events": [],
    }
    submission_path.write_text(json.dumps(submission, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Mock agent read context for {context['member']['person_id']} in {context['group']['group_id']}.")
    print(f"Context: {context_path.relative_to(root)}")
    print(f"Draft:   {submission_path.relative_to(root)}")
    if not args.submit:
        print("No event was created. Inspect the JSON draft, then rerun with --submit to record it locally.")
        return 0

    submit_command = ["agent-submit", "--person-id", args.person_id, "--input-file", str(submission_path)]
    if args.remote:
        submit_command.extend(["--remote", args.remote])
    submitted = run_cli(root, *submit_command)
    if submitted.stdout:
        sys.stdout.write(submitted.stdout)
    if submitted.stderr:
        sys.stderr.write(submitted.stderr)
    return submitted.returncode


if __name__ == "__main__":
    raise SystemExit(main())
