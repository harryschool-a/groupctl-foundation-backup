import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import groupctl

class V1FeatureTests(unittest.TestCase):
    def make_root(self):
        td=tempfile.TemporaryDirectory(); root=Path(td.name)
        (root/'.group/assignment').mkdir(parents=True); (root/'.group/events').mkdir(parents=True); (root/'.group/members').mkdir(parents=True); (root/'.group/local').mkdir(parents=True)
        (root/'.group/group.json').write_text(json.dumps({'protocol_version':'0.1','group_id':'G-1','canonical_branch':'main','assignment_file':'.group/assignment/assignment.md'}))
        (root/'.group/assignment/assignment.md').write_text('Build a small feature.')
        for pid in ['P1','P2']:
            (root/'.group/members'/f'{pid}.json').write_text(json.dumps({'protocol_version':'0.1','group_id':'G-1','person_id':pid,'display_name':pid}))
        return td,root

    def test_task_event_validation(self):
        event={'protocol_version':'0.1','event_id':'E-20260101T000000Z-P1-aaaa','event_type':'task_assigned','group_id':'G-1','person_id':'P1','created_at':'2026-01-01T00:00:00Z','related_events':[], 'task_id':'T-1','title':'Test','assignee_id':'P2','status':'open','depends_on':[]}
        self.assertEqual(groupctl.validate_event(event, Path(event['event_id']+'.json')), [])

    def test_task_create_and_list(self):
        td,root=self.make_root()
        try:
            args=type('A',(),{'root':str(root),'person_id':'P1','assignee_id':'P2','task_id':'T-1','title':'Write tests','status':'open','depends_on':[],'related_event':[]})()
            self.assertEqual(groupctl.command_task_create(args),0)
            out=io.StringIO()
            with contextlib.redirect_stdout(out): self.assertEqual(groupctl.command_tasks(type('A',(),{'root':str(root),'remote':None})()),0)
            self.assertIn('T-1 [open] -> P2',out.getvalue())
        finally: td.cleanup()

    def test_dashboard_is_local_artifact(self):
        td,root=self.make_root()
        try:
            args=type('A',(),{'root':str(root),'remote':None,'output':'report.html'})()
            self.assertEqual(groupctl.command_dashboard(args),0)
            text=(root/'report.html').read_text(encoding='utf-8')
            self.assertIn('groupctl v1.0 dashboard',text)
        finally: td.cleanup()

if __name__=='__main__': unittest.main()
