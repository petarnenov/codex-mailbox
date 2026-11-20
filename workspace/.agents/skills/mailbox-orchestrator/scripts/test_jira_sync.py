import tempfile
import unittest
from pathlib import Path

import jira_sync


class JiraSyncTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_start_assigns_and_targets_in_progress(self):
        request = jira_sync.queue(self.root, 'GEO-1', 'start')
        self.assertEqual('In Progress', request['target_status'])
        self.assertTrue(request['assign_current_user'])
        self.assertEqual([request], jira_sync.pending(self.root))

    def test_pr_and_verified_target_review_and_closed_without_assigning(self):
        review = jira_sync.queue(self.root, 'GEO-1', 'pr')
        closed = jira_sync.queue(self.root, 'GEO-1', 'verified')
        self.assertEqual('Development Peer Review', review['target_status'])
        self.assertEqual('Closed', closed['target_status'])
        self.assertFalse(review['assign_current_user'] or closed['assign_current_user'])

    def test_done_moves_request_to_audit_trail(self):
        request = jira_sync.queue(self.root, 'GEO-1', 'verified')
        jira_sync.done(self.root, request['id'], 'applied', 'Closed via transition 2')
        self.assertEqual([], jira_sync.pending(self.root))
        self.assertTrue((self.root / 'jira-sync' / 'done' / f"{request['id']}.json").exists())

    def test_done_requires_detail(self):
        request = jira_sync.queue(self.root, 'GEO-1', 'pr')
        with self.assertRaises(ValueError):
            jira_sync.done(self.root, request['id'], 'skipped', ' ')

    def test_unknown_event_is_rejected(self):
        with self.assertRaises(ValueError):
            jira_sync.queue(self.root, 'GEO-1', 'reopen')


if __name__ == '__main__':
    unittest.main()
