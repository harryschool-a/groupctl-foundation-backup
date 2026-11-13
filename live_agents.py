"""Live, provider-neutral LLM agent runner for groupctl v1.1.

Uses the OpenAI-compatible Chat Completions HTTP shape so local Ollama servers and
compatible hosted endpoints can participate without a provider SDK. Model output is
never executed automatically: implementers produce reviewed Git patch artifacts.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import groupctl

CONFIG_SCHEMA_VERSION = 1
DEFAULT_TIMEOUT = 180
MAX_AGENTS = 8
MAX_CONTEXT_FILES = 16
MAX_FILE_CHARS = 9000
MAX_TOTAL_SOURCE_CHARS = 65000
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
ALLOWED_SOURCE_SUFFIXES = {
    ".py", ".md", ".rst", ".toml", ".json", ".yaml", ".yml", ".js", ".ts",
    ".tsx", ".jsx", ".go", ".rs", ".java", ".cs", ".cpp", ".c", ".h",
    ".hpp", ".html", ".css", ".scss", ".sh", ".ps1", ".sql", ".xml",
}
SECRET_NAME_PARTS = ("secret", "credential", "token", "private", "password", "id_rsa", "apikey")


def _safe_agent_id(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and all(
        ch in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for ch in value
    )


def _git(root: Path, *args: str):
    return groupctl._run_git(root, *args)


def _git_output(root: Path, *args: str) -> str:
    result = _git(root, *args)
    if result.returncode:
        raise ValueError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def _task_for(root: Path, task_id: str, person_id: str, remote: str | None = None) -> dict[str, Any]:
    events, errors = groupctl._load_agent_events(root, remote)
    if errors:
        raise ValueError("Cannot start agent while collaboration events are invalid: " + "; ".join(errors))
    task_events = [e for e in events if e.get("event_type") == "task_assigned" and e.get("task_id") == task_id]
    if not task_events:
        raise ValueError(f"Unknown task_id {task_id!r}. Create it first with `python groupctl.py task-create`.")
    task = max(task_events, key=lambda e: (groupctl._event_time_key(e), e.get("event_id", "")))
    if task.get("assignee_id") != person_id:
        raise ValueError(f"Task {task_id} is assigned to {task.get('assignee_id')}, not {person_id}.")
    if task.get("status") not in {"open", "in_progress"}:
        raise ValueError(f"Task {task_id} is {task.get('status')}; only open or in_progress tasks can be run.")
    return task


def _latest_change(root: Path, change_id: str, remote: str | None = None) -> dict[str, Any]:
    events, errors = groupctl._load_agent_events(root, remote)
    if errors:
        raise ValueError("Cannot load changes while collaboration events are invalid: " + "; ".join(errors))
    change = next((e for e in events if e.get("event_type") == "change_published" and e.get("change_id") == change_id), None)
    if not change:
        raise ValueError(f"Unknown change_id {change_id!r}.")
    return change


def _safe_source_snapshot(root: Path) -> list[dict[str, str]]:
    """Read a bounded set of tracked text source files, excluding secrets and metadata."""
    result = _git(root, "ls-files", "-z")
    if result.returncode:
        raise ValueError("Live code proposals require a Git working repository.")
    paths = [p for p in result.stdout.split("\0") if p]
    included: list[dict[str, str]] = []
    total = 0
    for raw in sorted(paths):
        rel = PurePosixPath(raw.replace("\\", "/"))
        lower_parts = [part.lower() for part in rel.parts]
        if not rel.parts or rel.is_absolute() or ".." in rel.parts:
            continue
        if any(part in {".git", ".group", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"} for part in lower_parts):
            continue
        if any(part.startswith(".env") or any(secret in part for secret in SECRET_NAME_PARTS) for part in lower_parts):
            continue
        if rel.suffix.lower() not in ALLOWED_SOURCE_SUFFIXES:
            continue
        path = root.joinpath(*rel.parts)
        try:
            if not path.is_file() or path.stat().st_size > MAX_FILE_CHARS * 4:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        text = text[:MAX_FILE_CHARS]
        if total + len(text) > MAX_TOTAL_SOURCE_CHARS:
            break
        included.append({"path": rel.as_posix(), "content": text})
        total += len(text)
        if len(included) >= MAX_CONTEXT_FILES:
            break
    return included


def _task_prompt(root: Path, person_id: str, agent_id: str, task_id: str, role: str,
                 change_id: str | None = None, remote: str | None = None) -> tuple[str, str, dict[str, Any]]:
    context = groupctl.build_agent_context(root, person_id, remote=remote, limit=60, include_instructions=True)
    task = _task_for(root, task_id, person_id, remote)
    base_head = _git_output(root, "rev-parse", "HEAD")
    repo = {
        "branch": _git_output(root, "branch", "--show-current"),
        "head": base_head,
        "source_files": _safe_source_snapshot(root) if role == "implementer" else [],
    }
    if role == "implementer":
        if repo["branch"] == context["group"]["canonical_branch"]:
            raise ValueError("Implementer agents must work on a personal feature branch, not the canonical branch.")
        system = (
            "You are an AI software implementation agent working inside the groupctl collaboration protocol. "
            "Return ONLY one JSON object, with no Markdown fences or commentary. The task is to propose a code patch, "
            "not to execute commands or claim tests were run. Use a valid unified Git diff beginning with 'diff --git'. "
            "Do not modify .group metadata, .git, secrets, credentials, environment files, or files not needed by the task. "
            "Do not include destructive commands. If insufficient context, return event_type='finding' and explain what is missing. "
            "For a code proposal use event_type='code_proposal' and payload keys: summary, patch, files_changed, test_plan, risk_level. "
            "risk_level must be low, medium, or high. The patch must be based on the supplied current HEAD. "
            "Do not claim to have applied the patch or run tests."
        )
    elif role == "reviewer":
        if not change_id:
            raise ValueError("Reviewer role requires --change-id.")
        change = _latest_change(root, change_id, remote)
        diff = _git(root, "show", "--format=fuller", "--find-renames", change["commit"])
        if diff.returncode:
            raise ValueError("Could not inspect target change commit: " + diff.stderr.strip())
        diff_text = diff.stdout[:45000]
        context["target_change"] = {k: change.get(k) for k in ("change_id", "person_id", "agent_id", "branch", "commit", "summary", "files_changed", "interface_changes", "known_issues")}
        context["target_change_diff"] = diff_text
        system = (
            "You are an independent AI code reviewer. Return ONLY one JSON object, no Markdown fences. "
            "Use event_type='review'; payload must contain change_id, verdict, summary, issues, tests_run. "
            "verdict must be accept, accept_with_changes, reject, or needs_more_evidence. "
            "Review only the supplied evidence; do not claim tests were executed unless the evidence explicitly shows it. "
            "Look for correctness, regressions, security, edge cases, interface compatibility, and missing tests. "
            "Do not modify files or approve your own agent's change."
        )
    else:
        system = (
            "You are an AI engineering analyst. Return ONLY one JSON object, no Markdown fences. "
            "Use event_type='finding' and payload keys summary and evidence (array of strings). "
            "State uncertainty explicitly. Do not claim to have run tests or modified files."
        )
    user_payload = {
        "agent_id": agent_id,
        "role": role,
        "task": {k: task.get(k) for k in ("task_id", "title", "status", "depends_on")},
        "group_context": context,
        "repository": repo,
        "requested_change_id": change_id,
        "output_contract": {
            "implementer": {"event_type": "code_proposal", "payload": {"summary": "...", "patch": "unified git diff", "files_changed": ["relative/path"], "test_plan": ["command"], "risk_level": "low|medium|high"}},
            "reviewer": {"event_type": "review", "payload": {"change_id": "...", "verdict": "accept|accept_with_changes|reject|needs_more_evidence", "summary": "...", "issues": [], "tests_run": []}},
            "analyst": {"event_type": "finding", "payload": {"summary": "...", "evidence": []}},
        }[role],
    }
    return system, json.dumps(user_payload, ensure_ascii=False), {"base_commit": base_head, "task": task}


def _endpoint(base_url: str) -> str:
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base_url must be an absolute http:// or https:// URL.")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Non-local provider endpoints must use HTTPS.")
    return base_url.rstrip("/") + "/chat/completions"


def call_openai_compatible(base_url: str, model: str, messages: list[dict[str, str]],
                           *, api_key: str | None = None, timeout: int = DEFAULT_TIMEOUT,
                           max_tokens: int = 5000) -> str:
    """Call an OpenAI-compatible Chat Completions endpoint and return message content."""
    if not model.strip():
        raise ValueError("model must be non-empty.")
    if timeout < 5 or timeout > 900:
        raise ValueError("timeout must be between 5 and 900 seconds.")
    if max_tokens < 256 or max_tokens > 32000:
        raise ValueError("max_tokens must be between 256 and 32000.")
    body = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    request = urllib.request.Request(_endpoint(base_url), data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        detail = exc.read(3000).decode("utf-8", errors="replace")
        raise ValueError(f"Provider returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ValueError(f"Could not reach AI provider: {exc}") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("Provider response exceeded the 8 MiB safety limit.")
    try:
        decoded = json.loads(raw.decode("utf-8"))
        content = decoded["choices"][0]["message"]["content"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise ValueError("Provider response did not match the expected Chat Completions response format.") from exc
    if isinstance(content, list):
        # Some compatible endpoints return content as an array of text blocks.
        content = "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Provider returned an empty assistant message.")
    return content.strip()


def _parse_model_json(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Agent response was not valid JSON: {exc.msg} at line {exc.lineno}.") from exc
    if not isinstance(result, dict):
        raise ValueError("Agent response must be a JSON object.")
    return result


def _safe_patch_paths(patch: str) -> list[str]:
    """Extract and validate every path in a unified Git diff."""
    paths: list[str] = []

    def normalize_and_validate(raw: str) -> str | None:
        raw = raw.strip()
        if raw == "/dev/null":
            return None
        if raw.startswith(("a/", "b/")):
            raw = raw[2:]
        path = PurePosixPath(raw)
        normalized = path.as_posix()
        lower_parts = [part.lower() for part in path.parts]
        if (
            not raw
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in raw
            or not path.parts
            or ":" in path.parts[0]
            or any(part in {".git", ".group"} for part in lower_parts)
            or normalized.startswith(("/", "~"))
        ):
            raise ValueError(f"Patch target is not permitted: {normalized or raw}")
        if any(part.startswith(".env") or any(secret in part for secret in SECRET_NAME_PARTS) for part in lower_parts):
            raise ValueError(f"Patch target appears to contain a secret: {normalized}")
        return normalized

    for line in patch.splitlines():
        if line.startswith("diff --git "):
            match = re.match(r"^diff --git a/(.+) b/(.+)$", line)
            if not match:
                raise ValueError("Patch contains an invalid diff --git header.")
            for raw in match.groups():
                normalized = normalize_and_validate(raw)
                if normalized:
                    paths.append(normalized)
        elif line.startswith(("--- ", "+++ ")):
            raw = line[4:].split("\t", 1)[0].strip()
            normalized = normalize_and_validate(raw)
            if normalized:
                paths.append(normalized)

    if not paths:
        raise ValueError("Patch must contain at least one 'diff --git' section.")
    return sorted(set(paths))


def _store_code_proposal(root: Path, agent_id: str, person_id: str, task_id: str,
                         response: dict[str, Any], base_commit: str) -> dict[str, Any]:
    payload = response.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("Model code_proposal payload must be an object.")
    patch = payload.pop("patch", None)
    if not isinstance(patch, str) or not patch.strip():
        raise ValueError("Code proposal must contain a non-empty unified diff in payload.patch.")
    paths = _safe_patch_paths(patch)
    declared_paths = payload.get("files_changed", paths)
    if not isinstance(declared_paths, list) or any(not isinstance(x, str) for x in declared_paths):
        raise ValueError("files_changed must be an array of repository-relative paths.")
    # Use paths read from the patch as the authoritative list.
    proposal_id = "PR-" + uuid.uuid4().hex[:12]
    proposal_dir = root / ".group" / "proposals"
    proposal_dir.mkdir(parents=True, exist_ok=True)
    patch_path = proposal_dir / f"{proposal_id}.patch"
    patch_bytes = (patch.rstrip() + "\n").encode("utf-8")
    with patch_path.open("xb") as handle:
        handle.write(patch_bytes)
    payload.update({
        "proposal_id": proposal_id,
        "task_id": task_id,
        "base_commit": base_commit,
        "patch_file": patch_path.relative_to(root).as_posix(),
        "patch_sha256": hashlib.sha256(patch_bytes).hexdigest(),
        "files_changed": paths,
        "test_plan": payload.get("test_plan", []),
        "risk_level": payload.get("risk_level", "medium"),
    })
    return response


def _mark_task_in_progress(root: Path, task: dict[str, Any], person_id: str, agent_id: str) -> str:
    """Append an in_progress task state when an agent starts an open task."""
    if task.get("status") == "in_progress":
        return task["event_id"]
    path = groupctl.create_event(root, "task_assigned", {
        "task_id": task["task_id"],
        "title": task["title"],
        "assignee_id": task["assignee_id"],
        "status": "in_progress",
        "depends_on": task.get("depends_on", []),
    }, person_id, [task["event_id"]], agent_id=agent_id)
    return groupctl.read_json(path)["event_id"]


def _session_event(root: Path, person_id: str, agent_id: str, session_id: str,
                   status: str, provider: str, summary: str, actions: list[str],
                   related: list[str] | None = None) -> Path:
    return groupctl.create_event(root, "agent_session", {
        "session_id": session_id,
        "provider": provider,
        "status": status,
        "summary": summary,
        "actions": actions,
    }, person_id, related or [], agent_id=agent_id)


def _run_one(root: Path, *, person_id: str, agent_id: str, task_id: str, role: str,
             model: str, base_url: str, api_key_env: str = "", timeout: int = DEFAULT_TIMEOUT,
             max_tokens: int = 5000, change_id: str | None = None, remote: str | None = None) -> dict[str, Any]:
    # The provider's secret is read only from the process environment and never saved.
    api_key = os.environ.get(api_key_env) if api_key_env else None
    if api_key_env and not api_key:
        raise ValueError(f"API key environment variable {api_key_env!r} is not set.")
    system, user, meta = _task_prompt(root, person_id, agent_id, task_id, role, change_id, remote)
    current_task = meta["task"]
    claimed_by = current_task.get("agent_id")
    if current_task.get("status") == "in_progress" and claimed_by and claimed_by != agent_id:
        raise ValueError(f"Task {task_id} is already in progress under agent {claimed_by!r}; resume with that agent or have a human reopen/reassign the task.")
    task_event_id = _mark_task_in_progress(root, current_task, person_id, agent_id)
    session_id = "AS-" + uuid.uuid4().hex[:12]
    started = _session_event(root, person_id, agent_id, session_id, "started", "openai-compatible",
                             f"Agent {agent_id} started task {task_id} ({role}).", [f"task:{task_id}"], [task_event_id])
    try:
        content = call_openai_compatible(base_url, model, [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ], api_key=api_key, timeout=timeout, max_tokens=max_tokens)
        response = _parse_model_json(content)
        related = response.get("related_events", [])
        if not isinstance(related, list):
            raise ValueError("Agent related_events must be an array.")
        if task_event_id not in related:
            response["related_events"] = [*related, task_event_id]
        event_type = response.get("event_type")
        if role == "implementer" and event_type == "code_proposal":
            response = _store_code_proposal(root, agent_id, person_id, task_id, response, meta["base_commit"])
        elif role == "implementer" and event_type == "finding":
            pass  # The model can safely report that it lacks enough information.
        elif role == "reviewer" and event_type != "review":
            raise ValueError("Reviewer agent must return event_type='review'.")
        elif role == "analyst" and event_type != "finding":
            raise ValueError("Analyst agent must return event_type='finding'.")
        event_path = groupctl.submit_agent_event(
            root, person_id, response, agent_id=agent_id,
            remote=remote,
        )
        submitted = groupctl.read_json(event_path)
        _session_event(root, person_id, agent_id, session_id, "completed", "openai-compatible",
                       f"Agent {agent_id} completed task {task_id} and submitted {submitted['event_type']}.",
                       [f"event:{submitted['event_id']}", f"task:{task_id}"], [groupctl.read_json(started)["event_id"], submitted["event_id"]])
        return {"agent_id": agent_id, "status": "completed", "event_id": submitted["event_id"],
                "event_type": submitted["event_type"], "proposal_id": submitted.get("proposal_id"),
                "summary": submitted.get("summary", "")}
    except Exception as exc:
        _session_event(root, person_id, agent_id, session_id, "failed", "openai-compatible",
                       f"Agent {agent_id} failed task {task_id}: {exc}", [f"task:{task_id}"], [groupctl.read_json(started)["event_id"]])
        raise


def _agent_config_path(root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return path


def load_agents_config(root: Path, config_path: Path) -> list[dict[str, Any]]:
    try:
        config = groupctl.read_json(config_path)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    if not isinstance(config, dict) or config.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise ValueError("Agent config must be an object with schema_version: 1.")
    agents = config.get("agents")
    if not isinstance(agents, list) or not 1 <= len(agents) <= MAX_AGENTS:
        raise ValueError(f"Agent config must contain between 1 and {MAX_AGENTS} agents.")
    seen: set[str] = set()
    seen_tasks: set[str] = set()
    validated: list[dict[str, Any]] = []
    for index, raw in enumerate(agents):
        if not isinstance(raw, dict):
            raise ValueError(f"agents[{index}] must be an object.")
        item = dict(raw)
        required = ("agent_id", "person_id", "task_id", "role", "model", "base_url")
        missing = [key for key in required if not isinstance(item.get(key), str) or not item[key].strip()]
        if missing:
            raise ValueError(f"agents[{index}] is missing non-empty fields: {', '.join(missing)}")
        if not _safe_agent_id(item["agent_id"]):
            raise ValueError(f"agents[{index}].agent_id is not path-safe.")
        if item["agent_id"] in seen:
            raise ValueError(f"Duplicate agent_id: {item['agent_id']}")
        seen.add(item["agent_id"])
        if item["task_id"] in seen_tasks:
            raise ValueError(f"Duplicate task_id in agent config: {item['task_id']}; assign each concurrent agent a distinct task.")
        seen_tasks.add(item["task_id"])
        if item["role"] not in {"implementer", "reviewer", "analyst"}:
            raise ValueError(f"agents[{index}].role must be implementer, reviewer, or analyst.")
        if item["role"] == "reviewer" and not isinstance(item.get("change_id"), str):
            raise ValueError(f"Reviewer {item['agent_id']} must specify change_id.")
        if item.get("provider", "openai-compatible") != "openai-compatible":
            raise ValueError(f"agents[{index}].provider must be 'openai-compatible'.")
        groupctl._resolve_person_id(root, item["person_id"])
        item.setdefault("timeout", DEFAULT_TIMEOUT)
        item.setdefault("max_tokens", 5000)
        item.setdefault("api_key_env", "")
        if not isinstance(item["timeout"], int) or not 5 <= item["timeout"] <= 900:
            raise ValueError(f"agents[{index}].timeout must be from 5 to 900 seconds.")
        if not isinstance(item["max_tokens"], int) or not 256 <= item["max_tokens"] <= 32000:
            raise ValueError(f"agents[{index}].max_tokens must be from 256 to 32000.")
        _endpoint(item["base_url"])
        validated.append(item)
    return validated


def command_agent_run(args) -> int:
    root = Path(args.root).resolve()
    try:
        result = _run_one(root, person_id=args.person_id, agent_id=args.agent_id,
                          task_id=args.task_id, role=args.role, model=args.model,
                          base_url=args.base_url, api_key_env=args.api_key_env,
                          timeout=args.timeout, max_tokens=args.max_tokens,
                          change_id=args.change_id)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Agent {result['agent_id']}: {result['status']}")
    print(f"Event: {result['event_id']} ({result['event_type']})")
    if result.get("proposal_id"):
        print(f"Code proposal: {result['proposal_id']} (not applied)")
        print("Inspect the proposal, then use agent-apply with --human-approved on a feature branch.")
    return 0


def command_agents_run(args) -> int:
    root = Path(args.root).resolve()
    if args.max_workers < 1 or args.max_workers > MAX_AGENTS:
        print(f"ERROR: --max-workers must be between 1 and {MAX_AGENTS}.", file=sys.stderr)
        return 1
    try:
        config_path = _agent_config_path(root, args.config_file)
        agents = load_agents_config(root, config_path)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Starting {len(agents)} live agent(s) with at most {args.max_workers} concurrent request(s).")
    results: list[dict[str, Any]] = []
    failures: list[tuple[str, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(args.max_workers, len(agents))) as pool:
        future_map = {
            pool.submit(_run_one, root, person_id=a["person_id"], agent_id=a["agent_id"],
                        task_id=a["task_id"], role=a["role"], model=a["model"],
                        base_url=a["base_url"], api_key_env=a.get("api_key_env", ""),
                        timeout=a["timeout"], max_tokens=a["max_tokens"],
                        change_id=a.get("change_id")): a["agent_id"]
            for a in agents
        }
        for future in concurrent.futures.as_completed(future_map):
            agent_id = future_map[future]
            try:
                result = future.result()
                results.append(result)
                print(f"  OK   {agent_id}: {result['event_type']} event {result['event_id']}")
            except Exception as exc:
                failures.append((agent_id, str(exc)))
                print(f"  FAIL {agent_id}: {exc}", file=sys.stderr)
    print(f"Completed: {len(results)}; failed: {len(failures)}")
    return 1 if failures else 0


def command_agent_publish(args) -> int:
    root = Path(args.root).resolve()
    try:
        config = groupctl._load_valid_group(root)
        person_id = groupctl._resolve_person_id(root, args.person_id)
        if not _safe_agent_id(args.agent_id):
            raise ValueError("agent_id must be path-safe.")
        branch = _git_output(root, "branch", "--show-current")
        if branch == config["canonical_branch"]:
            raise ValueError("Publish agent work from a personal feature branch, not the canonical branch.")
        commit = _git_output(root, "rev-parse", "HEAD")
        canonical_ref = f"refs/heads/{config['canonical_branch']}"
        canonical_head = _git_output(root, "rev-parse", canonical_ref)
        changed = _git_output(root, "diff", "--name-only", f"{canonical_head}..{commit}").splitlines()
        if not changed:
            raise ValueError("No committed file changes found between canonical HEAD and this branch.")
        status = _git_output(root, "status", "--porcelain", "--untracked-files=all")
        unrelated = []
        for line in status.splitlines():
            path_text = line[3:].strip().strip('"') if len(line) >= 4 else ""
            normalized = path_text.replace("\\", "/")
            allowed_metadata = normalized.startswith((".group/events/", ".group/proposals/", ".group/local/"))
            if path_text and not allowed_metadata:
                unrelated.append(path_text)
        if unrelated:
            raise ValueError("Commit or set aside unrelated working-tree changes first: " + ", ".join(unrelated[:12]))
        short = commit[:7]
        change_id = "C-" + short
        payload = {
            "change_id": change_id,
            "branch": branch,
            "commit": commit,
            "summary": args.summary,
            "files_changed": sorted(set(changed)),
            "interface_changes": [],
            "tests_run": args.test_run,
            "known_issues": args.known_issue,
            "proposed_for_integration": True,
        }
        path = groupctl.create_event(root, "change_published", payload, person_id, [], agent_id=args.agent_id)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Published {change_id} from {branch} at {commit}.")
    print(f"Agent: {args.agent_id}; event: {path.relative_to(root)}")
    print("The change remains a proposal until an independent review and verified integration.")
    return 0


def command_agent_apply(args) -> int:
    root = Path(args.root).resolve()
    if not args.human_approved:
        print("ERROR: applying a model-generated patch requires --human-approved after inspecting the patch.", file=sys.stderr)
        return 1
    try:
        config = groupctl._load_valid_group(root)
        groupctl._resolve_person_id(root, args.person_id)
        events, errors = groupctl._load_agent_events(root)
        if errors:
            raise ValueError("Cannot apply while collaboration events are invalid: " + "; ".join(errors))
        proposal = next((e for e in events if e.get("event_type") == "code_proposal" and e.get("proposal_id") == args.proposal_id), None)
        if not proposal:
            raise ValueError(f"Unknown code proposal {args.proposal_id!r}.")
        branch = _git_output(root, "branch", "--show-current")
        if branch == config["canonical_branch"]:
            raise ValueError("Refusing to apply an AI patch directly on the canonical branch. Switch to a personal feature branch first.")
        head = _git_output(root, "rev-parse", "HEAD")
        if head != proposal["base_commit"] or head != args.expected_head:
            raise ValueError("HEAD changed since proposal creation. Re-run the agent against the new base or explicitly request a revised proposal.")
        status = _git_output(root, "status", "--porcelain", "--untracked-files=all")
        unsafe = []
        for line in status.splitlines():
            path_text = line[3:].strip().strip('"') if len(line) >= 4 else ""
            normalized = path_text.replace("\\", "/")
            allowed_metadata = normalized.startswith((".group/events/", ".group/proposals/", ".group/local/"))
            if path_text and not allowed_metadata:
                unsafe.append(path_text)
        if unsafe:
            raise ValueError("Working tree has unrelated changes; commit or set them aside before applying: " + ", ".join(unsafe[:12]))
        patch_path = (root / proposal["patch_file"]).resolve()
        proposal_root = (root / ".group" / "proposals").resolve()
        if proposal_root not in patch_path.parents or not patch_path.is_file():
            raise ValueError("Proposal patch file is missing or outside .group/proposals/.")
        patch_bytes = patch_path.read_bytes()
        if hashlib.sha256(patch_bytes).hexdigest() != proposal["patch_sha256"]:
            raise ValueError("Proposal patch file digest does not match its immutable event.")
        _safe_patch_paths(patch_bytes.decode("utf-8"))
        check = _git(root, "apply", "--check", "--whitespace=error-all", str(patch_path))
        if check.returncode:
            raise ValueError("Git rejected the patch during preflight: " + check.stderr.strip())
        apply = _git(root, "apply", "--whitespace=error-all", str(patch_path))
        if apply.returncode:
            raise ValueError("Git failed to apply patch: " + apply.stderr.strip())
        groupctl.create_event(root, "agent_session", {
            "session_id": "AP-" + uuid.uuid4().hex[:12],
            "provider": "agent-patch-review",
            "status": "completed",
            "summary": f"Human-approved code proposal {args.proposal_id} applied to {branch}; changes remain uncommitted.",
            "actions": ["human-approved patch apply", f"proposal:{args.proposal_id}", "git apply --check passed"],
        }, args.person_id, [proposal["event_id"]], agent_id="human-approved-apply")
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Applied proposal {args.proposal_id} to {branch}.")
    print("Changes are in the working tree only; inspect, run tests, then commit and publish them yourself.")
    return 0
