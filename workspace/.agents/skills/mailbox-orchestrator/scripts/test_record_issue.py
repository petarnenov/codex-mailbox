import json
import tempfile
import unittest
from pathlib import Path

from record_issue import main


class RecordIssueTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / 'epics' / 'EPIC-1' / 'issues.json'
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({'issues': [
            {'key': 'GEO-1', 'local_status': 'in_progress', 'blockers': ['depends on GEO-2', 'needs token']},
            {'key': 'GEO-2', 'local_status': 'in_progress'}]}))

    def tearDown(self):
        self.temp.cleanup()

    def issue(self, key):
        return next(i for i in json.loads(self.path.read_text())['issues'] if i['key'] == key)

    def run_command(self, *args):
        main(['--root', str(self.root), '--epic', 'EPIC-1', *args])

    def test_prerequisites_become_depends_on_and_replace_textual_dependency_blockers(self):
        self.run_command('--issue', 'GEO-1', 'depends-on', 'GEO-2')
        issue = self.issue('GEO-1')
        self.assertEqual(issue['depends_on'], ['GEO-2'])
        self.assertEqual(issue['blockers'], ['needs token'])

    def test_verified_records_passed_status_and_evidence(self):
        self.run_command('--issue', 'GEO-2', 'verified', '--evidence', 'PR #1 merge abc', 'report r1')
        issue = self.issue('GEO-2')
        self.assertEqual(issue['local_status'], 'verified_done')
        self.assertEqual(issue['verification']['status'], 'passed')
        self.assertEqual(issue['evidence'], ['PR #1 merge abc', 'report r1'])

    def test_rejects_unknown_issue_self_dependency_and_empty_evidence(self):
        with self.assertRaises(ValueError):
            self.run_command('--issue', 'GEO-9', 'depends-on', 'GEO-2')
        with self.assertRaises(ValueError):
            self.run_command('--issue', 'GEO-1', 'depends-on', 'GEO-1')
        with self.assertRaises(ValueError):
            self.run_command('--issue', 'GEO-2', 'verified', '--evidence', ' ')


if __name__ == '__main__':
    unittest.main()
