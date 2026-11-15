"""Regression coverage for exact links, execution reporting and honest verification."""
import server
from test_server import Fixture


class ReconciliationTests(Fixture):
    def task(self, key, **extra):
        self.put(f'tasks/p/{key}.json', dict(id=key, **extra))

    def test_reverse_only_link_blocks_verified_issue_and_exposes_execution(self):
        self.epic('E', ['A'], True, [{'key': 'A', 'local_status': 'verified_done',
                                     'verification': {'status': 'passed', 'reason': 'Integration checks passed'}, 'evidence': ['proof']}])
        self.task('T', issue_key='A', status='in_progress')
        result = server.build_dashboard(self.root)
        issue = result['issues'][0]
        self.assertEqual(['T'], issue['task_ids'])
        self.assertEqual('verified_done', issue['recorded_local_status'])
        self.assertEqual('awaiting_verification', issue['local_status'])
        self.assertFalse(issue['verified'])
        self.assertIn('T', issue['verification_reason'])
        self.assertEqual('Integration checks passed', issue['recorded_verification_reason'])
        self.assertEqual(0, result['totals']['percent'])
        self.assertEqual('issue', result['tasks'][0]['mapping_kind'])

    def test_aliases_and_duplicate_snapshots_union_before_verification(self):
        record = {'key': 'A', 'local_status': 'verified_done', 'verification': 'passed', 'evidence': ['proof']}
        self.epic('E', ['A'], True, [dict(record, task_ids=['T1'], local_task_ids=['T2'])])
        self.epic('F', ['A'], True, [dict(record, local_task_ids=['T3'])])
        self.task('T1', status='done', evidence=['proof'])
        self.task('T2', status='done', evidence=['proof'])
        self.task('T3', status='done')
        issue = server.build_dashboard(self.root)['issues'][0]
        self.assertEqual(['T1', 'T2', 'T3'], issue['task_ids'])
        self.assertFalse(issue['verified'])
        self.assertEqual(['T3'], issue['task_execution']['without_completion_evidence'])
        self.assertEqual(3, issue['task_execution']['total'])

    def test_epic_only_unknown_and_unmapped_work_stay_out_of_issue_progress(self):
        self.epic('E', ['A'], True, [{'key': 'A'}])
        self.task('EPIC', issue_key='E', status='done', evidence=['proof'])
        self.task('UNKNOWN', issue_key='X', status='in_progress')
        self.task('LOCAL', status='done', evidence=['proof'])
        data = server.build_dashboard(self.root)
        tasks = {t['id']: t for t in data['tasks']}
        self.assertEqual('epic', tasks['EPIC']['mapping_kind'])
        self.assertEqual('E', tasks['EPIC']['epic_key'])
        self.assertEqual('unresolved', tasks['UNKNOWN']['mapping_kind'])
        self.assertEqual('unmapped', tasks['LOCAL']['mapping_kind'])
        self.assertEqual([], data['issues'][0]['task_ids'])
        self.assertEqual('pending', data['issues'][0]['local_status'])
        self.assertTrue(any('X' in warning for warning in data['warnings']))
        self.assertEqual(0, data['totals']['percent'])

    def test_forward_links_multi_issue_and_missing_tasks(self):
        self.epic('E', ['A', 'B'], True, [
            {'key': 'A', 'task_ids': ['T', 'missing'], 'local_status': 'verified_done',
             'verification': 'passed', 'evidence': ['proof']},
            {'key': 'B', 'local_task_ids': ['T']}])
        self.task('T', issue_keys=['A', 'B', 'A'], status='done', evidence=['proof'])
        data = server.build_dashboard(self.root)
        self.assertEqual(['A', 'B'], data['tasks'][0]['issue_keys'])
        a, b = data['issues']
        self.assertEqual(['missing'], a['task_execution']['missing'])
        self.assertEqual(1, b['task_execution']['total'])
        self.assertFalse(a['verified'])
        self.assertEqual('pending', b['recorded_local_status'])
        self.assertEqual('awaiting_verification', b['execution_status'])
        self.assertEqual(0, data['totals']['verified_issues'])

    def test_recorded_reason_and_provenance_and_issue_over_epic_key(self):
        self.epic('E', ['E'], True, [{'key': 'E', 'local_status': 'awaiting_verification',
                                    'verification': {'status': 'not_verified', 'reason': 'Integration check pending'},
                                    'updated_at': '2026-11-15T00:00:00Z'}])
        self.task('T', issue_key='E', status='blocked', blockers=['Need fixture'])
        data = server.build_dashboard(self.root)
        issue = data['issues'][0]
        self.assertEqual('issue', data['tasks'][0]['mapping_kind'])
        self.assertEqual('blocked', issue['execution_status'])
        self.assertEqual('Integration check pending', issue['recorded_verification_reason'])
        self.assertIn('T', issue['verification_reason'])
        self.assertEqual(['epics/E/issues.json'], issue['sources'])
        self.assertEqual('2026-11-15T00:00:00Z', issue['updated_at'])
        self.assertEqual(['Need fixture'], data['tasks'][0]['blockers'])

    def test_conflicting_statuses_never_become_verified_from_task_completion(self):
        self.epic('E', ['A'], True, [{'key': 'A', 'local_status': 'pending'}])
        self.epic('F', ['A'], True, [{'key': 'A', 'local_status': 'verified_done',
                                    'verification': 'passed', 'evidence': ['proof']}])
        self.task('T', issue_key='A', status='done', evidence=['proof'])
        issue = server.build_dashboard(self.root)['issues'][0]
        self.assertTrue(issue['conflict'])
        self.assertFalse(issue['verified'])
        self.assertEqual('awaiting_verification', issue['local_status'])

    def test_multi_epic_task_preserves_owner_and_unknown_array_keys(self):
        self.epic('E', ['A'], True, [{'key': 'A', 'projects': ['consumer']}])
        self.epic('F', ['B'], True, [{'key': 'B', 'projects': ['consumer']}])
        self.put('tasks/owner/T.json', {'id': 'T', 'issue_keys': ['A', 'B', 'UNKNOWN'],
                                      'status': 'in_progress'})
        data = server.build_dashboard(self.root)
        task = data['tasks'][0]
        self.assertEqual(['E', 'F'], task['epic_keys'])
        self.assertEqual(['A', 'B'], task['issue_keys'])
        self.assertEqual(['UNKNOWN'], task['unresolved_issue_keys'])
        self.assertEqual('unresolved', task['mapping_kind'])
        self.assertEqual(['T'], next(p for p in data['projects'] if p['id'] == 'owner')['task_ids'])
        self.assertTrue(any('UNKNOWN' in w for w in data['warnings']))
