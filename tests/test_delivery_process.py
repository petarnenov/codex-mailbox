"""Evidence-based delivery orientation remains separate from execution eligibility."""
import os
import server
from test_server import Fixture

class DeliveryProcessTests(Fixture):
    def setUp(self):
        super().setUp()
        self.put('projects.json', {'projects': [{'id': 'p', 'name': 'Project'}]})

    def build(self, raw=None, others=None):
        others = others or []
        self.epic('E', ['A'] + [i['key'] for i in others], True,
                  [{'key': 'A', 'title': 'Business change', 'projects': ['p'], **(raw or {})}] + others)
        return server.build_dashboard(self.root)

    def issue(self, raw=None, others=None):
        return next(i for i in self.build(raw, others)['issues'] if i['key'] == 'A')

    def test_absent_baseline_is_unknown_without_owner_or_verifier(self):
        issue = self.issue({'source_status': 'Closed'})
        d = issue['delivery']
        self.assertEqual('unknown', d['stage'])
        self.assertIsNone(d['owner'])
        self.assertIsNone(d['verification']['verifier'])
        self.assertEqual([], d['criteria'])
        self.assertFalse(issue['verified'])

    def test_all_explicit_stages_except_complete_preserved(self):
        for stage in ('uninvestigated', 'investigating', 'ready', 'implementation', 'review', 'verification', 'unknown'):
            with self.subTest(stage=stage):
                self.assertEqual(stage, self.issue({'delivery': {'stage': stage}})['delivery']['stage'])

    def test_unknown_stage_not_promoted_by_closed(self):
        self.assertEqual('unknown', self.issue({'source_status': 'Closed', 'delivery': {'stage': 'released'}})['delivery']['stage'])

    def test_partial_and_complete_baselines_not_verified_delivery(self):
        for status, stage in (('partial', 'investigating'), ('complete', 'verification')):
            with self.subTest(status=status):
                issue = self.issue({'baseline_status': status, 'baseline_assessment': 'Existing source assessment'})
                self.assertEqual(stage, issue['delivery']['stage'])
                self.assertTrue(issue['delivery']['stage_reason'])
                self.assertFalse(issue['verified'])

    def test_recorded_complete_without_acceptance_is_candidate(self):
        issue = self.issue({'delivery': {'stage': 'complete'}})
        self.assertEqual('verification', issue['delivery']['stage'])
        self.assertFalse(issue['verified'])

    def test_complete_requires_existing_verified_acceptance(self):
        issue = self.issue({'local_status': 'verified_done', 'verification': 'passed', 'evidence': ['acceptance.json']})
        self.assertTrue(issue['verified'])
        self.assertEqual('complete', issue['delivery']['stage'])

    def test_deferred_issue_has_deferred_stage_and_stays_in_scope(self):
        self.put('tasks/p/T.json', {'id': 'T', 'status': 'pending', 'issue_key': 'A'})
        data = self.build({'local_status': 'deferred', 'task_ids': ['T']})
        issue = next(i for i in data['issues'] if i['key'] == 'A')
        self.assertEqual('deferred', issue['local_status'])
        self.assertEqual('deferred', issue['delivery']['stage'])
        self.assertFalse(issue['verified'])
        self.assertEqual(1, data['totals']['known_issues'])

    def test_execution_evidence_selects_stage_without_accepting_issue(self):
        for status, evidence, stage in (('in_progress', [], 'implementation'), ('done', ['task-proof'], 'verification')):
            with self.subTest(status=status):
                self.put('tasks/p/T.json', {'id': 'T', 'status': status, 'evidence': evidence, 'issue_key': 'A'})
                issue = self.issue({'task_ids': ['T']})
                self.assertEqual(stage, issue['delivery']['stage'])
                self.assertFalse(issue['verified'])

    def test_blockers_orthogonal_to_stage(self):
        self.put('tasks/p/T.json', {'id': 'T', 'status': 'blocked', 'blockers': ['Quota stopped'], 'issue_key': 'A'})
        d = self.issue({'task_ids': ['T'], 'blockers': ['Owner decision'], 'delivery': {'stage': 'review'}})['delivery']
        self.assertEqual('review', d['stage'])
        self.assertTrue(d['blocked'])
        self.assertIn('Quota stopped', ' '.join(d['blockers']))
        self.assertIn('Owner decision', ' '.join(d['blockers']))

    def test_inherited_story_epic_prerequisites_visible(self):
        self.put('epics/E/dependencies.json', {'nodes': [{'id': 'milestone:release', 'status': 'unknown'}],
            'edges': [{'from': 'milestone:release', 'to': 'epic:E', 'kind': 'requires'}]})
        d = self.issue({'parent_key': 'S', 'delivery': {'stage': 'ready'}},
                       [{'key': 'S', 'depends_on': ['B']}, {'key': 'B', 'local_status': 'pending'}])['delivery']
        self.assertTrue(d['blocked'])
        self.assertIn('B', ' '.join(d['blockers']))
        self.assertIn('milestone:release', ' '.join(d['blockers']))
        self.assertEqual('ready', d['stage'])

    def test_shared_task_does_not_make_an_issue_its_own_prerequisite(self):
        self.put('tasks/p/t.json', {'id': 't', 'project': 'p', 'status': 'in_progress'})
        d = self.issue({'task_ids': ['t']},
                       [{'key': 'C', 'task_ids': ['t'], 'depends_on': ['A'], 'projects': ['p']}])['delivery']
        self.assertNotIn('Unmet prerequisite: issue:A', d['blockers'])

    def test_criterion_pass_requires_own_nonblank_evidence(self):
        d = self.issue({'delivery': {'criteria': [
            {'text': 'First', 'status': 'passed', 'evidence': []},
            {'text': 'Second', 'status': 'passed', 'evidence': [' ']},
            {'text': 'Third', 'status': 'passed', 'evidence': ['criterion-proof']}]}})['delivery']
        self.assertNotEqual('passed', d['criteria'][0]['status'])
        self.assertNotEqual('passed', d['criteria'][1]['status'])
        self.assertEqual('passed', d['criteria'][2]['status'])
        self.assertEqual(['criterion-proof'], d['criteria'][2]['evidence'])

    def test_issue_wide_evidence_not_copied_to_criteria(self):
        d = self.issue({'local_status': 'verified_done', 'verification': 'passed', 'evidence': ['issue-proof'],
                        'delivery': {'criteria': [{'text': 'No criterion proof'}]}})['delivery']
        self.assertEqual('unknown', d['criteria'][0]['status'])
        self.assertEqual([], d['criteria'][0]['evidence'])

    def test_original_rich_acceptance_is_readable_text(self):
        raw = {'type': 'doc', 'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': 'Original acceptance <img src=x onerror=alert(1)>'}]}]}
        d = self.issue({'acceptance_criteria': raw})['delivery']
        self.assertIsInstance(d['acceptance_criteria'], str)
        self.assertIn('Original acceptance', d['acceptance_criteria'])
        self.assertIn('<img', d['acceptance_criteria'])

    def test_explicit_detail_work_owner_remainder_and_action(self):
        d = self.issue({'delivery': {'existing_work': 'Existing source: branch X', 'remainder': 'Integration and acceptance',
                       'owner': 'Owner Alice', 'next_action': 'Review contract', 'verification': {'verifier': 'Verifier Bob'}}})['delivery']
        self.assertEqual('Existing source: branch X', d['existing_work'])
        self.assertEqual('Integration and acceptance', d['remainder'])
        self.assertEqual('Owner Alice', d['owner'])
        self.assertEqual('Review contract', d['next_action'])
        self.assertEqual('Verifier Bob', d['verification']['verifier'])

    def test_trace_absent_unknown_despite_task_title(self):
        self.put('tasks/p/T.json', {'id': 'T', 'title': 'Integrated tested production', 'status': 'done', 'evidence': ['task-proof']})
        trace = self.issue({'task_ids': ['T']})['delivery']['trace']
        self.assertEqual({'written', 'reviewed', 'integrated', 'tested_integrated'}, {x['step'] for x in trace})
        self.assertTrue(all(x['status'] == 'unknown' for x in trace))

    def test_trace_integrated_revision_match_exact(self):
        for revision, expected in (('revision-B', 'unknown'), ('revision-A', 'evidenced')):
            with self.subTest(revision=revision):
                d = self.issue({'delivery': {'trace': {
                    'written': {'evidence': ['source.diff'], 'revision': 'revision-A'},
                    'reviewed': {'evidence': ['review.json'], 'revision': 'revision-A'},
                    'integrated': {'evidence': ['merge.json'], 'revision': 'revision-A'},
                    'tested_integrated': {'evidence': ['tests.json'], 'revision': revision}}}})['delivery']
                trace = {x['step']: x for x in d['trace']}
                self.assertEqual('evidenced', trace['integrated']['status'])
                self.assertEqual(expected, trace['tested_integrated']['status'])
                self.assertEqual('evidenced', trace['reviewed']['status'])
                self.assertNotEqual('complete', d['stage'])

    def test_trace_missing_revision_or_proof_unknown(self):
        trace = self.issue({'delivery': {'trace': {'integrated': {'evidence': ['merge.json']},
                       'tested_integrated': {'revision': 'revision-A'}, 'reviewed': {'revision': 'A', 'evidence': [' ']}}}})['delivery']['trace']
        self.assertTrue(all(x['status'] == 'unknown' for x in trace))

    def test_conflicting_process_metadata_conservative(self):
        self.epic('E', ['A'], True, [{'key': 'A', 'delivery': {'stage': 'review', 'owner': 'Alice'}}])
        self.epic('F', ['A'], True, [{'key': 'A', 'delivery': {'stage': 'complete', 'owner': 'Bob'}}])
        data = server.build_dashboard(self.root)
        self.assertEqual('unknown', data['issues'][0]['delivery']['stage'])
        self.assertIsNone(data['issues'][0]['delivery']['owner'])
        self.assertTrue(data['delivery_warnings'])

    def test_declared_timestamps_retained_without_mtime(self):
        raw = {'delivery': {'freshness': {'jira': '2026-01-01T00:00:00Z', 'worker': 'invalid source timestamp', 'evidence': '2999-01-01T00:00:00Z'}}}
        first = self.issue(raw)['delivery']['freshness']
        os.utime(self.root / 'epics/E/issues.json', (1, 1))
        self.assertEqual(first, server.build_dashboard(self.root)['issues'][0]['delivery']['freshness'])
        self.assertEqual('2026-01-01T00:00:00Z', first['jira'])
        self.assertEqual('invalid source timestamp', first['worker'])
        self.assertEqual('2999-01-01T00:00:00Z', first['evidence'])

    def test_missing_timestamps_not_read_time(self):
        d = self.issue()['delivery']
        for source in ('jira', 'worker', 'evidence'):
            self.assertIsNone(d['freshness'][source])
        self.assertEqual('unknown', d['freshness']['worker_basis'])

    def test_ready_stage_does_not_change_graph_completion(self):
        data = self.build({'delivery': {'stage': 'ready'}})
        node = next(n for n in data['graph']['nodes'] if n['id'] == 'issue:A')
        self.assertFalse(node['ready'])
        self.assertFalse(data['issues'][0]['verified'])
        self.assertEqual('ready', data['issues'][0]['delivery']['stage'])

    def test_html_acceptance_readable_without_script_or_style_content(self):
        d = self.issue({'acceptance_criteria': '<p>First requirement</p><ul><li>Second requirement</li></ul><script>steal()</script><style>body{color:red}</style>'})['delivery']
        self.assertIn('First requirement', d['acceptance_criteria'])
        self.assertIn('Second requirement', d['acceptance_criteria'])
        self.assertNotIn('steal()', d['acceptance_criteria'])
        self.assertNotIn('color:red', d['acceptance_criteria'])

    def test_mixed_malformed_criteria_do_not_fabricate_outcomes(self):
        d = self.issue({'delivery': {'criteria': [None, 'not a criterion', {}, {'text': []},
            {'text': 'Failure recorded', 'status': 'failed'}, {'text': 'Pending criterion', 'status': 'pending'},
            {'text': 'Unsupported outcome', 'status': 'released', 'evidence': {'test': ['report.json']}}]}})['delivery']
        self.assertEqual(['failed', 'pending', 'unknown'], [c['status'] for c in d['criteria']])
        self.assertEqual(['report.json'], d['criteria'][2]['evidence'])

    def test_aliases_and_explicit_source_time_override_linked_task_proxy(self):
        self.put('tasks/p/T.json', {'id': 'T', 'status': 'pending', 'owner': {'displayName': 'Task owner'},
            'updated_at': '2026-02-02T00:00:00Z', 'issue_key': 'A'})
        raw = {'task_ids': ['T'], 'delivery_stage': 'review', 'source_updated_at': '2026-01-01T00:00:00Z',
               'evidence_updated_at': '2026-03-03T00:00:00Z'}
        d = self.issue(raw)['delivery']
        self.assertEqual('review', d['stage'])
        self.assertEqual('Task owner', d['owner'])
        self.assertEqual('linked_task_updated_at_proxy', d['freshness']['worker_basis'])
        self.assertEqual('2026-02-02T00:00:00Z', d['freshness']['worker'])
        explicit = self.issue({**raw, 'worker_updated_at': '2026-01-03T00:00:00Z'})['delivery']
        self.assertEqual('explicit_report_time', explicit['freshness']['worker_basis'])
        self.assertEqual('2026-01-03T00:00:00Z', explicit['freshness']['worker'])
        self.assertEqual('2026-03-03T00:00:00Z', explicit['freshness']['evidence'])

    def test_explicit_not_started_and_process_stage_alias(self):
        self.assertEqual('uninvestigated', self.issue({'investigation_status': 'not_started'})['delivery']['stage'])
        self.assertEqual('ready', self.issue({'process_stage': 'ready'})['delivery']['stage'])

    def test_dependency_cycle_reported_and_projection_terminates(self):
        d = self.issue({'depends_on': ['B']}, [{'key': 'B', 'depends_on': ['A']}])['delivery']
        self.assertTrue(d['blocked'])
        self.assertIn('cycle', ' '.join(d['blockers']).lower())

    def test_unknown_verification_outcome_not_fabricated_pending_or_passed(self):
        d = self.issue({'delivery': {'verification': {'status': 'deployed', 'verifier': {'display_name': 'Reviewer'}, 'evidence': ['unrelated-proof']}}})['delivery']
        self.assertEqual('unknown', d['verification']['status'])
        self.assertEqual('Reviewer', d['verification']['verifier'])

    def test_null_or_malformed_blockers_never_crash_or_become_character_blockers(self):
        for blockers in (None, 42, {}, 'No structured blocker'):
            with self.subTest(blockers=blockers):
                d = self.issue({'blockers': blockers})['delivery']
                self.assertFalse(d['blocked'])
                self.assertEqual([], d['blockers'])

    def test_worker_proxy_uses_actual_chronology_across_timezone_offsets(self):
        self.put('tasks/p/T1.json', {'id': 'T1', 'status': 'pending', 'updated_at': '2026-02-02T10:00:00+10:00'})
        self.put('tasks/p/T2.json', {'id': 'T2', 'status': 'pending', 'updated_at': '2026-02-02T02:00:00Z'})
        d = self.issue({'task_ids': ['T1', 'T2']})['delivery']
        self.assertEqual('2026-02-02T02:00:00Z', d['freshness']['worker'])
        self.assertEqual('linked_task_updated_at_proxy', d['freshness']['worker_basis'])

    def test_invalid_proxy_source_time_retained_for_explicit_ui_warning(self):
        self.put('tasks/p/T.json', {'id': 'T', 'status': 'pending', 'updated_at': 'source-time-invalid'})
        d = self.issue({'task_ids': ['T']})['delivery']
        self.assertEqual('source-time-invalid', d['freshness']['worker'])
        self.assertEqual('linked_task_updated_at_proxy', d['freshness']['worker_basis'])

    def test_process_only_conflict_warns_without_changing_dependency_graph_warnings(self):
        self.epic('E', ['A'], True, [{'key': 'A', 'delivery': {'stage': 'ready'}}])
        self.epic('F', ['A'], True, [{'key': 'A', 'delivery': {'stage': 'review'}}])
        data = server.build_dashboard(self.root)
        self.assertEqual([], data['warnings'])
        self.assertTrue(any('conflicting delivery metadata' in w for w in data['delivery_warnings']))
        self.assertFalse(next(n for n in data['graph']['nodes'] if n['id'] == 'issue:A')['ready'])
