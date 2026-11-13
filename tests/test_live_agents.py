import contextlib
import io
import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import groupctl
import live_agents


class _FakeHandler(BaseHTTPRequestHandler):
    response_content = ""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        assert body["messages"][0]["role"] == "system"
        payload = json.dumps({
            "choices": [{"message": {"content": self.response_content}}]
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        pass


class LiveAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        groupctl.initialize_repository(self.root, "G-LIVE", "P1", "Person One", "main", ".group/assignment/assignment.md")
        self._git("init", "-b", "main")
        self._git("config", "user.name", "Test User")
        self._git("config", "user.email", "test@example.invalid")
        (self.root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
        self._git("add", ".")
        self._git("commit", "-m", "baseline")
        self._git("switch", "-c", "people/P1/feature")
        self.base = self._git("rev-parse", "HEAD").stdout.strip()
        groupctl.create_event(self.root, "task_assigned", {
            "task_id": "T-IMPLEMENT", "title": "Add a live feature", "assignee_id": "P1",
            "status": "open", "depends_on": [],
        }, "P1", [])

    def tearDown(self):
        self.temp.cleanup()

    def _git(self, *args):
        result = subprocess.run(["git", *args], cwd=self.root, text=True, capture_output=True)
        if result.returncode:
            raise AssertionError(result.stderr)
        return result

    def _server(self, content):
        handler = type("Handler", (_FakeHandler,), {"response_content": content})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def cleanup_server():
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
        self.addCleanup(cleanup_server)
        return f"http://127.0.0.1:{server.server_port}/v1"

    def test_endpoint_rejects_remote_plain_http(self):
        with self.assertRaisesRegex(ValueError, "must use HTTPS"):
            live_agents._endpoint("http://example.com/v1")

    def test_parse_model_json_accepts_fenced_json(self):
        result = live_agents._parse_model_json('```json\n{"event_type":"finding","payload":{}}\n```')
        self.assertEqual(result["event_type"], "finding")

    def test_task_must_be_assigned_to_invoking_member(self):
        with self.assertRaisesRegex(ValueError, "not P2"):
            live_agents._task_for(self.root, "T-IMPLEMENT", "P2")

    def test_live_agent_creates_code_proposal_then_human_applies_patch(self):
        patch = (
            "diff --git a/app.py b/app.py\n"
            "--- a/app.py\n"
            "+++ b/app.py\n"
            "@@ -1 +1,2 @@\n"
            " VALUE = 1\n"
            "+LIVE_FEATURE = True\n"
        )
        response = {
            "event_type": "code_proposal",
            "payload": {
                "summary": "Add a live feature flag.",
                "patch": patch,
                "files_changed": ["app.py"],
                "test_plan": ["python -m unittest discover -s tests -v"],
                "risk_level": "low",
            },
            "related_events": [],
        }
        base_url = self._server(json.dumps(response))
        result = live_agents._run_one(
            self.root, person_id="P1", agent_id="coder-a", task_id="T-IMPLEMENT",
            role="implementer", model="test-model", base_url=base_url, timeout=8,
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["event_type"], "code_proposal")
        self.assertTrue(result["proposal_id"].startswith("PR-"))
        proposal = next(e for e in groupctl._load_agent_events(self.root)[0] if e.get("proposal_id") == result["proposal_id"])
        self.assertEqual(proposal["agent_id"], "coder-a")
        self.assertEqual((self.root / "app.py").read_text(encoding="utf-8"), "VALUE = 1\n")
        task_events = [e for e in groupctl._load_agent_events(self.root)[0] if e.get("event_type") == "task_assigned" and e.get("task_id") == "T-IMPLEMENT"]
        latest_task_event = max(
            task_events,
            key=lambda event: (groupctl._event_time_key(event), event.get("event_id", "")),
        )
        self.assertEqual(latest_task_event["status"], "in_progress")
        self.assertEqual(latest_task_event["agent_id"], "coder-a")
        args = type("Args", (), {
            "root": str(self.root), "proposal_id": result["proposal_id"], "person_id": "P1",
            "expected_head": self.base, "human_approved": True,
        })()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(live_agents.command_agent_apply(args), 0)
        self.assertIn("Applied proposal", output.getvalue())
        self.assertEqual((self.root / "app.py").read_text(encoding="utf-8"), "VALUE = 1\nLIVE_FEATURE = True\n")


    def test_agent_publish_records_current_feature_branch_and_agent_identity(self):
        (self.root / "app.py").write_text("VALUE = 1\nFEATURE = True\n", encoding="utf-8")
        self._git("add", "app.py")
        self._git("commit", "-m", "implement feature")
        args = type("Args", (), {
            "root": str(self.root), "person_id": "P1", "agent_id": "coder-alpha",
            "summary": "Implement the feature.", "test_run": ["python -m unittest"], "known_issue": [],
        })()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(live_agents.command_agent_publish(args), 0)
        events, errors = groupctl._load_agent_events(self.root)
        self.assertEqual(errors, [])
        change = next(e for e in events if e.get("event_type") == "change_published")
        self.assertEqual(change["agent_id"], "coder-alpha")
        self.assertEqual(change["branch"], "people/P1/feature")
        self.assertEqual(change["files_changed"], ["app.py"])

    def test_live_reviewer_uses_distinct_agent_identity(self):
        source_path = groupctl.create_event(self.root, "change_published", {
            "change_id": "C-REVIEW", "branch": "people/P1/feature", "commit": self.base,
            "summary": "A change to review", "files_changed": ["app.py"],
            "interface_changes": [], "tests_run": [], "known_issues": [],
            "proposed_for_integration": True,
        }, "P1", [], agent_id="coder-alpha")
        groupctl.create_event(self.root, "task_assigned", {
            "task_id": "T-REVIEW", "title": "Review the change", "assignee_id": "P1",
            "status": "open", "depends_on": [],
        }, "P1", [])
        response = {"event_type": "review", "payload": {
            "change_id": "C-REVIEW", "verdict": "needs_more_evidence",
            "summary": "Add a boundary case test.", "issues": ["Missing boundary test."], "tests_run": [],
        }, "related_events": []}
        base_url = self._server(json.dumps(response))
        result = live_agents._run_one(
            self.root, person_id="P1", agent_id="reviewer-beta", task_id="T-REVIEW",
            role="reviewer", model="test-model", base_url=base_url, change_id="C-REVIEW", timeout=8,
        )
        self.assertEqual(result["event_type"], "review")
        events, errors = groupctl._load_agent_events(self.root)
        self.assertEqual(errors, [])
        review = next(e for e in events if e.get("event_type") == "review")
        self.assertEqual(review["agent_id"], "reviewer-beta")
        self.assertIn(groupctl.read_json(source_path)["event_id"], review["related_events"])

    def test_in_progress_task_cannot_be_claimed_by_a_different_agent(self):
        task = live_agents._task_for(self.root, "T-IMPLEMENT", "P1")
        live_agents._mark_task_in_progress(self.root, task, "P1", "coder-alpha")
        with self.assertRaisesRegex(ValueError, "already in progress under agent 'coder-alpha'"):
            live_agents._run_one(
                self.root, person_id="P1", agent_id="coder-beta", task_id="T-IMPLEMENT",
                role="analyst", model="test-model", base_url="http://127.0.0.1:1/v1", timeout=8,
            )

    def test_agents_config_rejects_duplicate_task_ids(self):
        config_path = self.root / ".group/agents.json"
        config_path.write_text(json.dumps({"schema_version": 1, "agents": [
            {"agent_id": "analyst-a", "person_id": "P1", "task_id": "T-IMPLEMENT", "role": "analyst", "model": "m", "base_url": "http://localhost:11434/v1"},
            {"agent_id": "analyst-b", "person_id": "P1", "task_id": "T-IMPLEMENT", "role": "analyst", "model": "m", "base_url": "http://localhost:11434/v1"},
        ]}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate task_id"):
            live_agents.load_agents_config(self.root, config_path)

    def test_patch_rejects_secret_directory_and_file_header_mismatch(self):
        with self.assertRaisesRegex(ValueError, "secret"):
            live_agents._safe_patch_paths(
                "diff --git a/secrets/config.py b/secrets/config.py\n"
                "--- a/secrets/config.py\n+++ b/secrets/config.py\n"
            )
        with self.assertRaisesRegex(ValueError, "secret"):
            live_agents._safe_patch_paths(
                "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/.env.production\n"
            )

    def test_agent_apply_requires_explicit_human_approval(self):
        args = type("Args", (), {
            "root": str(self.root), "proposal_id": "PR-NOPE", "person_id": "P1",
            "expected_head": self.base, "human_approved": False,
        })()
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            self.assertEqual(live_agents.command_agent_apply(args), 1)
        self.assertIn("--human-approved", output.getvalue())


    def test_multiple_agents_run_concurrently_against_one_endpoint(self):
        groupctl.create_event(self.root, "task_assigned", {
            "task_id": "T-ANALYZE", "title": "Analyze a design alternative", "assignee_id": "P1",
            "status": "open", "depends_on": [],
        }, "P1", [])
        response = {"event_type": "finding", "payload": {
            "summary": "The implementation task has two independent areas.",
            "evidence": ["This is a deterministic fake-provider response."],
        }, "related_events": []}
        base_url = self._server(json.dumps(response))
        config = self.root / ".group/agents.json"
        config.write_text(json.dumps({"schema_version": 1, "agents": [
            {"agent_id": "analyst-a", "person_id": "P1", "task_id": "T-IMPLEMENT", "role": "analyst", "model": "m", "base_url": base_url, "timeout": 8},
            {"agent_id": "analyst-b", "person_id": "P1", "task_id": "T-ANALYZE", "role": "analyst", "model": "m", "base_url": base_url, "timeout": 8},
        ]}), encoding="utf-8")
        args = type("Args", (), {"root": str(self.root), "config_file": str(config), "max_workers": 2})()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(live_agents.command_agents_run(args), 0)
        self.assertIn("Completed: 2; failed: 0", out.getvalue())
        events, errors = groupctl._load_agent_events(self.root)
        self.assertEqual(errors, [])
        findings = [e for e in events if e.get("event_type") == "finding"]
        self.assertEqual({e.get("agent_id") for e in findings}, {"analyst-a", "analyst-b"})

    def test_distinct_agent_identity_can_submit_review_under_same_member(self):
        source = groupctl.create_event(self.root, "change_published", {
            "change_id": "C-AGENT-1", "branch": "people/P1/feature", "commit": self.base,
            "summary": "A contribution from coder A", "files_changed": ["app.py"],
            "interface_changes": [], "tests_run": [], "known_issues": [],
            "proposed_for_integration": True,
        }, "P1", [], agent_id="coder-a")
        review = groupctl.submit_agent_event(self.root, "P1", {
            "event_type": "review", "payload": {
                "change_id": "C-AGENT-1", "verdict": "needs_more_evidence",
                "summary": "Reviewer B requests a test for the boundary case.",
                "issues": ["Add a boundary-case test."], "tests_run": [],
            }, "related_events": [],
        }, agent_id="reviewer-b")
        review_event = groupctl.read_json(review)
        self.assertEqual(review_event["agent_id"], "reviewer-b")
        self.assertIn(groupctl.read_json(source)["event_id"], review_event["related_events"])
        with self.assertRaisesRegex(ValueError, "Self-review"):
            groupctl.submit_agent_event(self.root, "P1", {
                "event_type": "review", "payload": {
                    "change_id": "C-AGENT-1", "verdict": "accept", "summary": "Self review",
                    "issues": [], "tests_run": [],
                }, "related_events": [],
            }, agent_id="coder-a")

    def test_patch_target_rejects_group_metadata_and_traversal(self):
        with self.assertRaisesRegex(ValueError, "not permitted"):
            live_agents._safe_patch_paths("diff --git a/../outside.py b/../outside.py\n")
        with self.assertRaisesRegex(ValueError, "not permitted"):
            live_agents._safe_patch_paths("diff --git a/.group/group.json b/.group/group.json\n")

    def test_multi_agent_config_rejects_duplicate_agent_ids(self):
        config_path = self.root / ".group/agents.json"
        config_path.write_text(json.dumps({"schema_version": 1, "agents": [
            {"agent_id": "same", "person_id": "P1", "task_id": "T-IMPLEMENT", "role": "implementer", "model": "m", "base_url": "http://localhost:11434/v1"},
            {"agent_id": "same", "person_id": "P1", "task_id": "T-IMPLEMENT", "role": "analyst", "model": "m", "base_url": "http://localhost:11434/v1"},
        ]}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate agent_id"):
            live_agents.load_agents_config(self.root, config_path)


if __name__ == "__main__":
    unittest.main()
