import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import groupctl


class GroupConfigTests(unittest.TestCase):
    def test_valid_config_and_assignment_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".group/assignment").mkdir(parents=True)
            (root / ".group/assignment/assignment.md").write_text("# Assignment\n", encoding="utf-8")
            config = {
                "protocol_version": "0.1",
                "group_id": "G-12",
                "canonical_branch": "main",
                "assignment_file": ".group/assignment/assignment.md",
            }
            self.assertEqual(groupctl.validate_group_config(config, root), [])

    def test_missing_person_fields_are_reported(self):
        errors = groupctl.validate_group_config(
            {"protocol_version": "0.1", "group_id": "G-12"}, Path(".")
        )
        self.assertTrue(any("canonical_branch" in error for error in errors))
        self.assertTrue(any("assignment_file" in error for error in errors))


class EventValidationTests(unittest.TestCase):
    def valid_event(self):
        return {
            "protocol_version": "0.1",
            "event_id": "E-20261016T021530Z-P17-a91f",
            "event_type": "finding",
            "group_id": "G-12",
            "person_id": "P17",
            "created_at": "2026-10-16T02:15:30Z",
            "related_events": [],
            "summary": "A useful discovery.",
            "evidence": ["Reproduced in a test."],
        }

    def test_valid_common_envelope_and_finding_payload(self):
        event = self.valid_event()
        path = Path(f"{event['event_id']}.json")
        self.assertEqual(groupctl.validate_event(event, path), [])

    def test_missing_person_id_is_rejected(self):
        event = self.valid_event()
        del event["person_id"]
        errors = groupctl.validate_event(event)
        self.assertTrue(any("person_id" in error for error in errors))

    def test_unsupported_event_type_is_rejected(self):
        event = self.valid_event()
        event["event_type"] = "chat_dump"
        errors = groupctl.validate_event(event)
        self.assertTrue(any("event_type" in error for error in errors))

    def test_timestamp_must_have_timezone(self):
        event = self.valid_event()
        event["created_at"] = "2026-10-16T02:15:30"
        errors = groupctl.validate_event(event)
        self.assertTrue(any("timezone" in error for error in errors))

    def test_filename_must_match_event_id(self):
        event = self.valid_event()
        errors = groupctl.validate_event(event, Path("wrong-name.json"))
        self.assertTrue(any("filename must match event_id" in error for error in errors))

    def test_change_published_requires_documented_fields(self):
        event = self.valid_event()
        event.update({"event_type": "change_published", "summary": "Published", "evidence": []})
        errors = groupctl.validate_event(event)
        self.assertTrue(any("change_id" in error for error in errors))
        self.assertTrue(any("branch" in error for error in errors))
        self.assertTrue(any("proposed_for_integration" in error for error in errors))

    def test_review_rejects_unknown_verdict(self):
        event = self.valid_event()
        event.update({
            "event_type": "review", "change_id": "C-17", "verdict": "maybe",
            "summary": "Review", "issues": [], "tests_run": [],
        })
        errors = groupctl.validate_event(event)
        self.assertTrue(any("verdict must be one of" in error for error in errors))

    def test_all_documented_event_types_accept_their_contract_payloads(self):
        common = self.valid_event()
        payloads = {
            "change_published": {
                "change_id": "C-17", "branch": "people/P17/parser", "commit": "abc123",
                "summary": "Published parser", "files_changed": ["src/parser.py"],
                "interface_changes": [], "tests_run": ["python -m unittest"],
                "known_issues": [], "proposed_for_integration": True,
            },
            "finding": {"summary": "Found issue", "evidence": ["Reproduced"]},
            "question": {"question_id": "Q-1", "text": "Keep source positions?", "blocking": False},
            "answer": {"question_id": "Q-1", "text": "Yes."},
            "review": {"change_id": "C-17", "verdict": "accept", "summary": "Looks good", "issues": [], "tests_run": []},
            "test_result": {"scope": "main", "commit": "abc123", "commands": ["python -m unittest"], "automated_result": "pass", "passed": 2, "failed": 0, "skipped": 0, "human_checks_required": [], "summary": "Two passed"},
            "integration_result": {"change_id": "C-17", "target_branch": "people/P17/parser", "result": "success", "merge_commit": "def456", "conflicts": [], "verification": {"tests": "pass"}, "summary": "Integrated"},
            "blocker": {"summary": "Need interface decision", "requested_action": "Human chooses API", "blocking_change_id": "C-17"},
            "synthesis_candidate": {"synthesis_id": "S-001", "title": "Combine proposals", "problem_statement": "Need one compatible approach", "source_change_ids": ["C-17", "C-22"], "proposed_approach": "Compose both approaches", "alternatives_considered": ["Keep separate"], "tradeoffs": ["Adds an interface boundary"], "validation_plan": ["Run end-to-end tests"], "decision": "draft", "unresolved_concerns": []},
            "final_candidate": {"canonical_branch": "main", "canonical_commit": "a" * 40, "report_file": ".group/final/candidate.md", "summary": "Candidate", "completed_work": ["Feature"], "contributors": ["P17"], "test_evidence": ["Tests passed"], "known_limitations": [], "unresolved_concerns": []},
            "final_result": {"canonical_branch": "main", "canonical_commit": "a" * 40, "report_file": ".group/final/final_report.md", "initiated_by": "P17", "status": "completed", "summary": "Final", "test_evidence": ["Tests passed"], "known_limitations": []},
        }
        for event_type, payload in payloads.items():
            with self.subTest(event_type=event_type):
                event = {**common, "event_type": event_type, **payload}
                self.assertEqual(groupctl.validate_event(event, Path(f"{common['event_id']}.json")), [])

    def test_synthesis_candidate_requires_unique_sources_and_known_decision(self):
        event = self.valid_event()
        event.update({
            "event_type": "synthesis_candidate", "synthesis_id": "S-001",
            "title": "Combine proposals", "problem_statement": "Need one approach",
            "source_change_ids": ["C-17", "C-17"],
            "proposed_approach": "Compose them", "alternatives_considered": [],
            "tradeoffs": [], "validation_plan": [], "decision": "maybe",
            "unresolved_concerns": [],
        })
        errors = groupctl.validate_event(event)
        self.assertTrue(any("must not contain duplicates" in error for error in errors))
        self.assertTrue(any("decision must be one of" in error for error in errors))

    def test_unhashable_enum_values_are_reported_not_crashed(self):
        review = self.valid_event()
        review.update({"event_type": "review", "change_id": "C-17", "verdict": [], "summary": "Review", "issues": [], "tests_run": []})
        self.assertTrue(any("verdict must be one of" in error for error in groupctl.validate_event(review)))
        test_event = self.valid_event()
        test_event.update({"event_type": "test_result", "scope": "current_branch", "commit": "abc123", "automated_result": [], "commands": [], "passed": 0, "failed": 0, "skipped": 0, "human_checks_required": [], "summary": "bad enum"})
        self.assertTrue(any("automated_result must be one of" in error for error in groupctl.validate_event(test_event)))

    def test_test_result_counts_must_be_nonnegative_integers(self):
        event = self.valid_event()
        event.update({
            "event_type": "test_result", "scope": "current_branch", "commit": "abc1234",
            "commands": ["python -m unittest"], "automated_result": "pass",
            "passed": -1, "failed": 0, "skipped": 0, "human_checks_required": [],
            "summary": "Tests passed.",
        })
        errors = groupctl.validate_event(event)
        self.assertTrue(any("passed must be a non-negative integer" in error for error in errors))


class EventCreationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        groupctl.initialize_repository(
            self.root, "G-12", "P17", "Student A", "main",
            ".group/assignment/assignment.md",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_event_adds_common_envelope(self):
        path = groupctl.create_event(
            self.root, "finding",
            {"summary": "A useful discovery.", "evidence": ["A test reproduced it."]},
            None, [],
        )
        event = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(path.parent, self.root / ".group/events")
        self.assertEqual(event["event_type"], "finding")
        self.assertEqual(event["group_id"], "G-12")
        self.assertEqual(event["person_id"], "P17")
        self.assertEqual(event["related_events"], [])
        self.assertEqual(groupctl.validate_event(event, path), [])

    def test_create_event_refuses_payload_to_override_common_fields(self):
        with self.assertRaisesRegex(ValueError, "common envelope fields"):
            groupctl.create_event(
                self.root, "finding",
                {"protocol_version": "9.9", "summary": "A finding", "evidence": []},
                None, [],
            )

    def test_create_event_requires_explicit_person_when_multiple_members_exist(self):
        groupctl.write_json(self.root / ".group/members/P22.json", {
            "protocol_version": "0.1", "person_id": "P22", "display_name": "Student B",
            "joined_at": "2026-10-16T10:30:00+08:00",
        })
        with self.assertRaisesRegex(ValueError, "Supply --person-id explicitly"):
            groupctl.create_event(
                self.root, "finding", {"summary": "A finding", "evidence": []}, None, []
            )

    def test_write_json_refuses_overwrite(self):
        path = self.root / ".group/events/test.json"
        groupctl.write_json(path, {"first": True})
        with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
            groupctl.write_json(path, {"second": True})


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        groupctl.initialize_repository(
            self.root, "G-12", "P17", "Student A", "main",
            ".group/assignment/assignment.md",
        )
        for person_id, display_name in (("P22", "Student B"), ("P31", "Student C")):
            groupctl.write_json(self.root / f".group/members/{person_id}.json", {
                "protocol_version": "0.1", "person_id": person_id,
                "display_name": display_name, "joined_at": "2026-10-16T10:30:00+08:00",
            })

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_status(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = groupctl.main(["status", "--root", str(self.root), *args])
        return code, output.getvalue()

    def test_status_reports_review_integration_and_synthesis_separately(self):
        groupctl.create_event(self.root, "change_published", {
            "change_id": "C-17", "branch": "people/P17/parser", "commit": "a" * 40,
            "summary": "Add parser", "files_changed": ["src/parser.py"],
            "interface_changes": [], "tests_run": ["python -m unittest"],
            "known_issues": [], "proposed_for_integration": True,
        }, "P17", [])
        groupctl.create_event(self.root, "review", {
            "change_id": "C-17", "verdict": "accept", "summary": "API is compatible",
            "issues": [], "tests_run": ["python -m unittest"],
        }, "P22", [])
        groupctl.create_event(self.root, "integration_result", {
            "change_id": "C-17", "target_branch": "main", "result": "success",
            "merge_commit": "b" * 40, "conflicts": [],
            "verification": {"tests": "pass", "semantic_review": "pass"},
            "summary": "Integrated into canonical branch",
        }, "P31", [])
        groupctl.create_event(self.root, "test_result", {
            "scope": "canonical main", "commit": "b" * 40,
            "commands": ["python -m unittest discover -s tests -v"],
            "automated_result": "pass", "passed": 12, "failed": 0,
            "skipped": 0, "human_checks_required": [],
            "summary": "All tests passed on the recorded commit.",
        }, "P31", [])
        groupctl.create_event(self.root, "synthesis_candidate", {
            "synthesis_id": "S-001", "title": "Parser and renderer pipeline",
            "problem_statement": "Connect independent contributions",
            "source_change_ids": ["C-17"],
            "proposed_approach": "Compose the parser with a renderer",
            "alternatives_considered": ["Keep them separate"],
            "tradeoffs": ["Adds a small integration boundary"],
            "validation_plan": ["Test the end-to-end pipeline"],
            "decision": "draft", "unresolved_concerns": ["Confirm function naming"],
        }, "P17", [])

        code, output = self.run_status()
        self.assertEqual(code, 0, output)
        self.assertIn("C-17 [reported integrated on canonical branch; Git ancestry not verified]", output)
        self.assertIn("Latest review: accept", output)
        self.assertIn("S-001 [draft]", output)
        self.assertIn("LATEST TEST EVIDENCE", output)
        self.assertIn("12 passed, 0 failed, 0 skipped", output)
        self.assertIn("Evidence applies to the recorded commit", output)
        self.assertIn("does not merge or integrate code", output)
        self.assertIn("Finalization: not finalized", output)

    @unittest.skipUnless(shutil.which("git"), "Git is required for canonical ancestry status test")
    def test_status_uses_git_ancestry_to_verify_canonical_inclusion(self):
        def git(*args):
            return subprocess.run(
                ["git", *args], cwd=self.root, check=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )

        git("init", "-b", "main")
        git("config", "user.name", "Groupctl Status Test")
        git("config", "user.email", "groupctl-status@example.invalid")
        git("add", ".group")
        git("commit", "-m", "initialize group")
        git("switch", "-c", "people/P17/feature")
        feature = self.root / "feature.py"
        feature.write_text("VALUE = 42\n", encoding="utf-8")
        git("add", "feature.py")
        git("commit", "-m", "add feature")
        feature_commit = git("rev-parse", "HEAD").stdout.strip()
        groupctl.create_event(self.root, "change_published", {
            "change_id": "C-ANCESTOR", "branch": "people/P17/feature",
            "commit": feature_commit, "summary": "Add a small feature",
            "files_changed": ["feature.py"], "interface_changes": [],
            "tests_run": ["not yet run"], "known_issues": [],
            "proposed_for_integration": True,
        }, "P17", [])
        git("add", ".group/events")
        git("commit", "-m", "publish feature event")

        code, output = self.run_status()
        self.assertEqual(code, 0, output)
        self.assertIn("C-ANCESTOR [awaiting review]", output)

        git("switch", "main")
        git("merge", "--no-ff", "people/P17/feature", "-m", "integrate feature")
        code, output = self.run_status()
        self.assertEqual(code, 0, output)
        self.assertIn("C-ANCESTOR [present on canonical branch (verified by Git ancestry)]", output)

    def test_status_identifies_changes_awaiting_review_and_rejected_changes(self):
        groupctl.create_event(self.root, "change_published", {
            "change_id": "C-22", "branch": "people/P17/docs", "commit": "c" * 40,
            "summary": "Update documentation", "files_changed": ["README.md"],
            "interface_changes": [], "tests_run": ["documentation link check"],
            "known_issues": [], "proposed_for_integration": True,
        }, "P17", [])
        code, output = self.run_status()
        self.assertEqual(code, 0, output)
        self.assertIn("C-22 [awaiting review]", output)

        groupctl.create_event(self.root, "review", {
            "change_id": "C-22", "verdict": "reject", "summary": "Contains a false usage example",
            "issues": ["Example command does not exist"], "tests_run": [],
        }, "P22", [])
        code, output = self.run_status()
        self.assertEqual(code, 0, output)
        self.assertIn("C-22 [rejected in latest review]", output)

@unittest.skipUnless(shutil.which("git"), "Git is required for remote-event integration tests")
class RemoteEventTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
        self.root = base / "work"
        self.bare = base / "remote.git"
        self.root.mkdir()
        subprocess.run(["git", "init", "--bare", str(self.bare)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        subprocess.run(["git", "init", "-b", "main", str(self.root)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.git("config", "user.name", "Groupctl Test")
        self.git("config", "user.email", "groupctl-test@example.invalid")
        # Keep the test's committed blob bytes exact across Windows/Linux hosts.
        self.git("config", "core.autocrlf", "false")
        groupctl.initialize_repository(
            self.root, "G-12", "P17", "Student A", "main",
            ".group/assignment/assignment.md",
        )
        self.git("add", ".")
        self.git("commit", "-m", "initialize test repository")
        self.git("remote", "add", "origin", str(self.bare))
        self.git("push", "--set-upstream", "origin", "main")
        self.git("checkout", "-b", "people/P17/demo")
        groupctl.create_event(
            self.root, "finding",
            {"summary": "Remote branch event", "evidence": ["Created in an integration test."]},
            None, [],
        )
        self.git("add", ".group/events")
        self.git("commit", "-m", "publish test event")
        self.git("push", "--set-upstream", "origin", "people/P17/demo")

    def current_event(self):
        event_path = next((self.root / ".group/events").glob("*.json"))
        return event_path, json.loads(event_path.read_text(encoding="utf-8"))

    def publish_file_on_branch(self, branch: str, relative_path: str, content: bytes, message: str):
        """Publish test bytes on a branch, then refresh remote-tracking refs."""
        self.git("checkout", branch)
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        self.git("add", "--", relative_path)
        self.git("commit", "-m", message)
        self.git("push", "origin", branch)
        self.git("fetch", "origin")

    def tearDown(self):
        self.temp_dir.cleanup()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def run_remote_events(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = groupctl.main(["remote-events", "--root", str(self.root), *args])
        return code, output.getvalue()

    def test_discovers_event_on_remote_personal_branch(self):
        code, output = self.run_remote_events("--remote", "origin", "--new-only")
        self.assertEqual(code, 0, output)
        self.assertIn("NEW", output)
        self.assertIn("finding", output)
        self.assertIn("people/P17/demo", output)

    def test_mark_seen_checkpoint_prevents_relisting_known_events(self):
        code, first = self.run_remote_events("--remote", "origin", "--mark-seen")
        self.assertEqual(code, 0, first)
        self.assertIn("Checkpoint updated", first)
        code, second = self.run_remote_events("--remote", "origin", "--new-only")
        self.assertEqual(code, 0, second)
        self.assertIn("No new remote events since the last local checkpoint.", second)
        self.assertNotIn("finding", second)

    def test_malformed_remote_event_is_reported_and_not_checkpointed(self):
        self.publish_file_on_branch(
            "people/P17/demo", ".group/events/E-malformed.json", b"{ this is not JSON }\n",
            "add malformed event fixture",
        )

        code, output = self.run_remote_events("--remote", "origin", "--new-only", "--mark-seen")

        self.assertEqual(code, 1)
        self.assertIn("invalid JSON", output)
        self.assertIn("Checkpoint not updated", output)
        self.assertFalse((self.root / ".group/local/known_remote_events_origin.json").exists())

    def test_remote_event_with_mismatched_group_id_is_rejected(self):
        _, event = self.current_event()
        event["event_id"] = "E-20261021T000000Z-P17-bad1"
        event["group_id"] = "G-OTHER"
        relative_path = f".group/events/{event['event_id']}.json"
        content = (json.dumps(event, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        self.publish_file_on_branch(
            "people/P17/demo", relative_path, content, "add mismatched group event fixture",
        )

        code, output = self.run_remote_events("--remote", "origin", "--new-only")

        self.assertEqual(code, 1)
        self.assertIn("group_id 'G-OTHER' does not match local group 'G-12'", output)
        self.assertIn("INVALID", output)

    def test_same_event_id_with_different_raw_line_endings_is_immutability_conflict(self):
        event_path, _event = self.current_event()
        # Save the exact bytes that were committed on people/P17/demo.
        original_bytes = event_path.read_bytes()
        self.assertIn(b"\n", original_bytes)
        self.assertNotIn(b"\r\n", original_bytes)

        # Create another remote branch from main, which has no finding event, then
        # publish the same JSON/event ID with CRLF bytes. JSON data is equivalent,
        # but a published event is immutable at the byte level.
        self.git("checkout", "-b", "people/P22/line-ending-conflict", "main")
        duplicate_path = self.root / ".group/events" / event_path.name
        duplicate_path.parent.mkdir(parents=True, exist_ok=True)
        duplicate_path.write_bytes(original_bytes.replace(b"\n", b"\r\n"))
        relative_path = duplicate_path.relative_to(self.root).as_posix()
        self.git("add", "--", relative_path)
        self.git("commit", "-m", "add byte-different duplicate event fixture")
        self.git("push", "--set-upstream", "origin", "people/P22/line-ending-conflict")
        self.git("fetch", "origin")

        code, output = self.run_remote_events("--remote", "origin", "--new-only")

        self.assertEqual(code, 1)
        self.assertIn("IMMUTABILITY CONFLICT", output)
        self.assertIn(event_path.stem, output)




class AgentBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        groupctl.initialize_repository(
            self.root, "G-12", "P17", "Student A", "main",
            ".group/assignment/assignment.md",
        )
        (self.root / "AGENT_INSTRUCTIONS.md").write_text("# Agent rules\nDo not merge without approval.\n", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def add_member(self, person_id="P18", display_name="Student B"):
        member = {
            "protocol_version": groupctl.PROTOCOL_VERSION,
            "person_id": person_id,
            "display_name": display_name,
            "joined_at": "2026-11-13T00:00:00Z",
        }
        path = self.root / ".group" / "members" / f"{person_id}.json"
        path.write_text(json.dumps(member), encoding="utf-8")

    def create_change_event(self, *, person_id="P17", change_id="C-source"):
        return groupctl.create_event(
            self.root,
            "change_published",
            {
                "change_id": change_id,
                "branch": "people/P17/source",
                "commit": "abc123",
                "summary": "A source contribution",
                "files_changed": ["src/example.py"],
                "interface_changes": [],
                "tests_run": [],
                "known_issues": [],
                "proposed_for_integration": True,
            },
            person_id,
            [],
        )

    def test_context_contains_assignment_identity_and_safety_rules(self):
        context = groupctl.build_agent_context(self.root, "P17")
        self.assertEqual(context["tool_version"], "1.0.0")
        self.assertEqual(context["group"]["group_id"], "G-12")
        self.assertEqual(context["member"]["person_id"], "P17")
        self.assertIn("# Group Assignment", context["assignment"]["text"])
        self.assertIn("# Agent rules", context["agent_instructions"])
        self.assertTrue(any("human" in rule.lower() for rule in context["safety_rules"]))
        self.assertFalse(context["repository"]["available"])

    def test_context_can_omit_instructions(self):
        context = groupctl.build_agent_context(self.root, "P17", include_instructions=False)
        self.assertIsNone(context["agent_instructions"])

    def test_context_rejects_invalid_event_state(self):
        bad_path = self.root / ".group" / "events" / "broken.json"
        bad_path.write_text("{not json", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "invalid collaboration events"):
            groupctl.build_agent_context(self.root, "P17")

    def test_agent_can_submit_valid_finding(self):
        path = groupctl.submit_agent_event(
            self.root,
            "P17",
            {"event_type": "finding", "payload": {"summary": "A useful finding", "evidence": ["Observed locally"]}},
        )
        event = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(event["event_type"], "finding")
        self.assertEqual(event["person_id"], "P17")
        self.assertEqual(groupctl.validate_event(event, path), [])

    def test_agent_cannot_submit_finalization_event(self):
        with self.assertRaisesRegex(ValueError, "does not permit"):
            groupctl.submit_agent_event(
                self.root, "P17",
                {"event_type": "final_result", "payload": {}},
            )

    def test_agent_cannot_override_common_envelope(self):
        with self.assertRaisesRegex(ValueError, "common envelope fields"):
            groupctl.submit_agent_event(
                self.root, "P17",
                {"event_type": "finding", "payload": {
                    "protocol_version": "9.9", "summary": "Bad", "evidence": []
                }},
            )

    def test_agent_bridge_rejects_self_review(self):
        self.create_change_event()
        with self.assertRaisesRegex(ValueError, "Self-review is not allowed"):
            groupctl.submit_agent_event(
                self.root, "P17",
                {"event_type": "review", "payload": {
                    "change_id": "C-source", "verdict": "accept", "summary": "Looks good",
                    "issues": [], "tests_run": [],
                }},
            )

    def test_agent_bridge_allows_independent_review_and_links_source_event(self):
        self.create_change_event()
        self.add_member()
        path = groupctl.submit_agent_event(
            self.root, "P18",
            {"event_type": "review", "payload": {
                "change_id": "C-source", "verdict": "accept_with_changes", "summary": "Needs one clarification",
                "issues": ["Document the return type"], "tests_run": [],
            }},
        )
        event = json.loads(path.read_text(encoding="utf-8"))
        source = next(
            p for p in (self.root / ".group/events").glob("*.json")
            if json.loads(p.read_text(encoding="utf-8")).get("event_type") == "change_published"
            and json.loads(p.read_text(encoding="utf-8")).get("change_id") == "C-source"
        )
        source_event_id = json.loads(source.read_text(encoding="utf-8"))["event_id"]
        self.assertIn(source_event_id, event["related_events"])

    def init_git_repository(self):
        subprocess.run(["git", "init", "-b", "main", str(self.root)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Agent Bridge Test"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "agent-bridge@example.invalid"], check=True)
        (self.root / "tracked.txt").write_text("bridge test\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "tracked.txt"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-m", "test fixture"], check=True, stdout=subprocess.PIPE)
        return subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"], check=True,
            text=True, stdout=subprocess.PIPE,
        ).stdout.strip()

    @unittest.skipUnless(shutil.which("git"), "Git is required for agent Git-evidence tests")
    def test_agent_change_published_requires_existing_commit_and_branch(self):
        commit = self.init_git_repository()
        path = groupctl.submit_agent_event(
            self.root, "P17",
            {"event_type": "change_published", "payload": {
                "change_id": "C-git", "branch": "main", "commit": commit,
                "summary": "Publish bridge implementation", "files_changed": ["tracked.txt"],
                "interface_changes": [], "tests_run": [], "known_issues": [],
                "proposed_for_integration": True,
            }},
        )
        event = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(event["commit"], commit)

    @unittest.skipUnless(shutil.which("git"), "Git is required for agent Git-evidence tests")
    def test_agent_test_result_requires_existing_commit(self):
        commit = self.init_git_repository()
        path = groupctl.submit_agent_event(
            self.root, "P17",
            {"event_type": "test_result", "payload": {
                "scope": "main", "commit": commit, "commands": ["python -m unittest"],
                "automated_result": "pass", "passed": 1, "failed": 0, "skipped": 0,
                "human_checks_required": [], "summary": "One test passed on the recorded commit.",
            }},
        )
        event = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(event["commit"], commit)

    @unittest.skipUnless(shutil.which("git"), "Git is required for agent Git-evidence tests")
    def test_agent_successful_integration_must_be_on_target_branch(self):
        commit = self.init_git_repository()
        self.create_change_event()
        integration_path = groupctl.submit_agent_event(
            self.root, "P17",
            {"event_type": "integration_result", "payload": {
                "change_id": "C-source", "target_branch": "main", "result": "success",
                "merge_commit": commit, "conflicts": [], "verification": {"tests": "pass"},
                "summary": "Verified on main.",
            }},
        )
        integration = json.loads(integration_path.read_text(encoding="utf-8"))
        self.assertEqual(integration["merge_commit"], commit)

    def test_agent_synthesis_requires_known_source_changes(self):
        payload = {
            "synthesis_id": "S-1", "title": "Combine", "problem_statement": "Need one approach",
            "source_change_ids": ["C-missing"], "proposed_approach": "Combine ideas",
            "alternatives_considered": [], "tradeoffs": [], "validation_plan": [],
            "decision": "draft", "unresolved_concerns": [],
        }
        with self.assertRaisesRegex(ValueError, "unknown"):
            groupctl.submit_agent_event(self.root, "P17", {"event_type": "synthesis_candidate", "payload": payload})

    def test_agent_context_cli_outputs_parseable_json(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = groupctl.main(["agent-context", "--root", str(self.root), "--person-id", "P17", "--no-instructions"])
        self.assertEqual(code, 0)
        decoded = json.loads(output.getvalue())
        self.assertEqual(decoded["member"]["person_id"], "P17")



@unittest.skipUnless(shutil.which("git"), "Git is required for finalization integration tests")
class FinalizationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        subprocess.run(["git", "init", "-b", "main", str(self.root)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.git("config", "user.name", "Groupctl Finalization Test")
        self.git("config", "user.email", "groupctl-final-test@example.invalid")
        self.git("config", "core.autocrlf", "false")
        groupctl.initialize_repository(
            self.root, "G-12", "P17", "Student A", "main",
            ".group/assignment/assignment.md",
        )
        (self.root / "src").mkdir()
        (self.root / "src/app.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "initial canonical code")
        self.canonical_commit = self.git("rev-parse", "HEAD").strip()
        (self.root / ".group/local/candidate_payload.json").write_text(json.dumps({
            "canonical_branch": "main",
            "canonical_commit": self.canonical_commit,
            "summary": "The group implemented a small verified program.",
            "completed_work": ["Implemented answer()"],
            "contributors": ["P17 (Student A)"],
            "test_evidence": ["python -m unittest discover -s tests -v: pass"],
            "known_limitations": [],
            "unresolved_concerns": [],
        }, indent=2), encoding="utf-8")
        code, output = self.run_groupctl(
            "final-candidate", "--payload-file", ".group/local/candidate_payload.json", "--person-id", "P17"
        )
        self.assertEqual(code, 0, output)
        self.candidate_event_path = max((self.root / ".group/events").glob("*.json"), key=lambda x: x.stat().st_mtime)
        self.git("add", ".group/final/candidate.md", self.candidate_event_path.relative_to(self.root).as_posix())
        self.git("commit", "-m", "record final candidate")

    def tearDown(self):
        self.temp_dir.cleanup()

    def git(self, *args):
        result = subprocess.run(["git", *args], cwd=self.root, check=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return result.stdout

    def run_groupctl(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = groupctl.main([args[0], "--root", str(self.root), *args[1:]])
        return code, output.getvalue()

    def final_payload(self, **updates):
        payload = {
            "canonical_branch": "main",
            "canonical_commit": self.canonical_commit,
            "summary": "The group implemented a small verified program.",
            "completed_work": ["Implemented answer()"],
            "contributors": ["P17 (Student A)"],
            "test_evidence": ["python -m unittest discover -s tests -v: pass"],
            "known_limitations": [],
            "status": "completed",
        }
        payload.update(updates)
        path = self.root / ".group/local/final_payload.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return ".group/local/final_payload.json"

    def test_candidate_creates_report_and_valid_event(self):
        self.assertTrue((self.root / ".group/final/candidate.md").is_file())
        events = [json.loads(p.read_text(encoding="utf-8")) for p in (self.root / ".group/events").glob("*.json")]
        candidates = [e for e in events if e["event_type"] == "final_candidate"]
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["canonical_commit"], self.canonical_commit)
        self.assertEqual(groupctl.validate_event(candidates[0]), [])

    def test_finalize_requires_explicit_human_confirmation(self):
        payload_path = self.final_payload()
        code, output = self.run_groupctl("finalize-confirmed", "--payload-file", payload_path, "--person-id", "P17")
        self.assertEqual(code, 1)
        self.assertIn("Human confirmation is required", output)
        self.assertFalse((self.root / ".group/final/final.json").exists())

    def test_finalize_writes_report_envelope_and_event_after_confirmation(self):
        payload_path = self.final_payload()
        code, output = self.run_groupctl(
            "finalize-confirmed", "--payload-file", payload_path, "--person-id", "P17", "--human-confirmed"
        )
        self.assertEqual(code, 0, output)
        report_path = self.root / ".group/final/final_report.md"
        envelope_path = self.root / ".group/final/final.json"
        self.assertTrue(report_path.is_file())
        envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
        self.assertEqual(envelope["canonical_commit"], self.canonical_commit)
        self.assertEqual(envelope["status"], "completed")
        self.assertEqual(groupctl.validate_final_records(self.root, groupctl.read_json(self.root / ".group/group.json")), [])
        events = [json.loads(p.read_text(encoding="utf-8")) for p in (self.root / ".group/events").glob("*.json")]
        results = [e for e in events if e["event_type"] == "final_result"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["canonical_commit"], self.canonical_commit)
        self.assertEqual(groupctl.validate_event(results[0]), [])

    def test_completed_status_requires_no_known_limitations(self):
        payload_path = self.final_payload(known_limitations=["One non-critical edge case is not supported."])
        code, output = self.run_groupctl(
            "finalize-confirmed", "--payload-file", payload_path, "--person-id", "P17", "--human-confirmed"
        )
        self.assertEqual(code, 1)
        self.assertIn("completed_with_known_limitations", output)

    def test_candidate_must_be_built_from_canonical_branch(self):
        self.git("checkout", "-b", "people/P17/experimental")
        payload = json.loads((self.root / ".group/local/candidate_payload.json").read_text(encoding="utf-8"))
        path = self.root / ".group/local/bad_candidate.json"
        payload["canonical_commit"] = self.git("rev-parse", "HEAD").strip()
        path.write_text(json.dumps(payload), encoding="utf-8")
        code, output = self.run_groupctl(
            "final-candidate", "--payload-file", ".group/local/bad_candidate.json", "--person-id", "P17"
        )
        self.assertEqual(code, 1)
        self.assertIn("configured canonical branch", output)

    def test_finalization_refuses_candidate_with_unresolved_concerns(self):
        payload = json.loads((self.root / ".group/local/candidate_payload.json").read_text(encoding="utf-8"))
        payload["unresolved_concerns"] = ["A published change is still unexplained."]
        payload["canonical_commit"] = self.git("rev-parse", "HEAD").strip()
        local_path = self.root / ".group/local/unresolved_candidate.json"
        local_path.write_text(json.dumps(payload), encoding="utf-8")
        code, output = self.run_groupctl("final-candidate", "--payload-file", ".group/local/unresolved_candidate.json", "--person-id", "P17", "--replace-candidate")
        self.assertEqual(code, 0, output)
        # Keep the candidate event committed as metadata, then the finalizer must
        # refuse final success because the latest proposal has unresolved concerns.
        candidate_events = list((self.root / ".group/events").glob("*.json"))
        newest_event = max(candidate_events, key=lambda x: x.stat().st_mtime)
        self.git("add", ".group/final/candidate.md", newest_event.relative_to(self.root).as_posix())
        self.git("commit", "-m", "revise final candidate with unresolved concern")
        final_path = self.final_payload(canonical_commit=payload["canonical_commit"])
        code, output = self.run_groupctl("finalize-confirmed", "--payload-file", final_path, "--person-id", "P17", "--human-confirmed")
        self.assertEqual(code, 1)
        self.assertIn("unresolved concerns", output)
        self.assertFalse((self.root / ".group/final/final.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
