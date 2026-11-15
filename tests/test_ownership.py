"""Ownership roles are independent recorded facts, never liveness or eligibility."""
import server
from test_server import Fixture

class OwnershipTests(Fixture):
    def setUp(self):
        super().setUp()
        self.put('projects.json', {'projects': [{'id': 'p', 'name': 'Project'}, {'id': 'q', 'name': 'Other project'}]})

    def build(self, raw=None, others=None):
        others = others or []
        self.epic('E', ['A'] + [i['key'] for i in others], True,
                  [{'key': 'A', 'title': 'Business change', 'projects': ['p'], **(raw or {})}] + others)
        return server.build_dashboard(self.root)

    def issue(self, raw=None, others=None):
        return next(i for i in self.build(raw, others)['issues'] if i['key'] == 'A')

    def roles(self, raw=None, others=None):
        return self.issue(raw, others)['delivery']['ownership']

    def test_absent_jira_not_loaded_and_other_roles_not_recorded(self):
        o = self.roles()
        self.assertEqual('not_loaded', o['jira']['status'])
        self.assertIsNone(o['jira']['name'])
        self.assertEqual('not_recorded', o['implementation']['status'])
        self.assertEqual('not_recorded', o['execution']['status'])

    def test_explicit_jira_null_unassigned_not_not_loaded(self):
        o = self.roles({'jira_assignee': None, 'jira_assignee_source': 'jira issue A', 'jira_assignee_retrieved_at': '2026-11-15T00:00:00Z'})
        self.assertEqual('unassigned', o['jira']['status'])
        self.assertIsNone(o['jira']['name'])
        self.assertEqual('jira issue A', o['jira']['source'])
        self.assertEqual('2026-11-15T00:00:00Z', o['jira']['retrieved_at'])

    def test_implementation_owner_is_independent_of_jira(self):
        o = self.roles({'implementation_owner': 'admin-center'})
        self.assertEqual('assigned', o['implementation']['status'])
        self.assertEqual('admin-center', o['implementation']['name'])
        self.assertEqual('not_loaded', o['jira']['status'])

    def test_linked_owner_session_id_is_recorded_execution_owner(self):
        self.put('tasks/p/T.json', {'id': 'T', 'status': 'pending', 'owner_session_id': 'full-session-identity-123', 'issue_key': 'A'})
        o = self.roles({'task_ids': ['T']})
        self.assertEqual('assigned', o['execution']['status'])
        self.assertIn('full-session-identity-123', str(o['execution']))
        self.assertIn('tasks/p/T.json', str(o['execution']))
        self.assertEqual('not_loaded', o['jira']['status'])

    def test_jira_assigned_name_source_and_read_time_preserved(self):
        o = self.roles({'jira_assignee': {'accountId': 'stable-1', 'displayName': 'Alice'},
                       'jira_assignee_source': 'jira read-only issue A', 'jira_assignee_retrieved_at': '2026-11-15T10:00:00Z'})
        self.assertEqual('assigned', o['jira']['status'])
        self.assertEqual('Alice', o['jira']['name'])
        self.assertEqual('jira read-only issue A', o['jira']['source'])
        self.assertEqual('2026-11-15T10:00:00Z', o['jira']['retrieved_at'])

    def test_account_id_only_is_assigned_identity_not_unassigned(self):
        o = self.roles({'jira_assignee': {'accountId': 'stable-account-only'}})
        self.assertEqual('assigned', o['jira']['status'])
        self.assertIn('stable-account-only', str(o['jira']))

    def test_malformed_jira_is_conflict_not_unassigned(self):
        for assignee in ({}, '', 42, [], {'displayName': ''}, {'accountId': []}):
            with self.subTest(assignee=assignee):
                self.assertEqual('conflict', self.roles({'jira_assignee': assignee})['jira']['status'])

    def duplicate(self, left, right):
        self.epic('E', ['A'], True, [{'key': 'A', **left}])
        self.epic('F', ['A'], True, [{'key': 'A', **right}])
        return server.build_dashboard(self.root)

    def test_same_stable_account_with_renamed_label_not_conflicting(self):
        data = self.duplicate({'jira_assignee': {'accountId': 'stable', 'displayName': 'Old name'}},
                              {'jira_assignee': {'accountId': 'stable', 'displayName': 'New name'}})
        self.assertEqual('assigned', data['issues'][0]['delivery']['ownership']['jira']['status'])

    def test_distinct_jira_accounts_conflict_even_when_labels_match(self):
        data = self.duplicate({'jira_assignee': {'accountId': 'one', 'displayName': 'Same label'}},
                              {'jira_assignee': {'accountId': 'two', 'displayName': 'Same label'}})
        o = data['issues'][0]['delivery']['ownership']
        self.assertEqual('conflict', o['jira']['status'])
        self.assertIsNone(o['jira']['name'])

    def test_null_and_assigned_jira_conflict_without_erasing_implementation(self):
        data = self.duplicate({'jira_assignee': None, 'implementation_owner': 'Project owner'},
                              {'jira_assignee': {'accountId': 'one'}, 'implementation_owner': 'Project owner'})
        o = data['issues'][0]['delivery']['ownership']
        self.assertEqual('conflict', o['jira']['status'])
        self.assertEqual('assigned', o['implementation']['status'])
        self.assertEqual('Project owner', o['implementation']['name'])

    def test_absent_jira_snapshot_does_not_conflict_with_loaded_snapshot(self):
        data = self.duplicate({}, {'jira_assignee': {'accountId': 'one', 'displayName': 'Alice'}})
        self.assertEqual('assigned', data['issues'][0]['delivery']['ownership']['jira']['status'])

    def test_implementation_conflict_does_not_erase_independent_jira_or_execution(self):
        self.put('tasks/p/T.json', {'id': 'T', 'status': 'pending', 'owner': 'Worker one', 'issue_key': 'A'})
        data = self.duplicate({'implementation_owner': 'p', 'task_ids': ['T'], 'jira_assignee': {'accountId': 'one', 'displayName': 'Alice'}},
                              {'implementation_owner': 'q', 'task_ids': ['T'], 'jira_assignee': {'accountId': 'one', 'displayName': 'Alice'}})
        o = data['issues'][0]['delivery']['ownership']
        self.assertEqual('conflict', o['implementation']['status'])
        self.assertEqual('assigned', o['jira']['status'])
        self.assertEqual('assigned', o['execution']['status'])

    def test_multiple_actual_linked_workers_are_not_conflict(self):
        self.put('tasks/p/T1.json', {'id': 'T1', 'status': 'pending', 'owner_session_id': 'worker-one', 'issue_key': 'A'})
        self.put('tasks/q/T2.json', {'id': 'T2', 'status': 'pending', 'owner': 'worker-two', 'issue_key': 'A'})
        o = self.roles({'task_ids': ['T1', 'T2'], 'projects': ['p', 'q']})
        self.assertEqual('assigned', o['execution']['status'])
        for value in ('worker-one', 'worker-two', 'T1', 'T2', 'tasks/p/T1.json', 'tasks/q/T2.json'):
            self.assertIn(value, str(o['execution']))

    def test_unlinked_worker_and_project_membership_never_invent_owner(self):
        self.put('tasks/p/OTHER.json', {'id': 'OTHER', 'owner_session_id': 'unrelated-worker', 'status': 'in_progress'})
        self.put('sessions/p.json', {'project': 'p', 'session_id': 'registered-session', 'last_seen': '2999-01-01T00:00:00Z'})
        o = self.roles({'projects': ['p', 'q'], 'parent_key': 'S'}, [{'key': 'S', 'jira_assignee': {'accountId': 'parent', 'displayName': 'Parent assignee'}}])
        self.assertEqual('not_loaded', o['jira']['status'])
        self.assertEqual('not_recorded', o['implementation']['status'])
        self.assertEqual('not_recorded', o['execution']['status'])

    def test_legacy_owner_never_becomes_jira_assignee(self):
        issue = self.issue({'owner': 'Legacy recorded local owner'})
        self.assertEqual('Legacy recorded local owner', issue['delivery']['owner'])
        self.assertEqual('not_loaded', issue['delivery']['ownership']['jira']['status'])

    def test_ownership_does_not_change_stage_graph_ready_or_verification(self):
        before = self.build({'delivery': {'stage': 'ready'}})
        after = self.build({'delivery': {'stage': 'ready'}, 'implementation_owner': 'p', 'jira_assignee': {'accountId': 'one'}})
        self.assertEqual(before['graph'], after['graph'])
        self.assertEqual(before['issues'][0]['verified'], after['issues'][0]['verified'])
        self.assertEqual(before['issues'][0]['delivery']['stage'], after['issues'][0]['delivery']['stage'])
        self.assertEqual(before['warnings'], after['warnings'])

    def test_retrieval_timestamp_does_not_replace_full_jira_snapshot_timestamp(self):
        issue = self.issue({'updated_at': '2026-01-01T00:00:00Z', 'source_updated_at': '2026-01-02T00:00:00Z',
                            'jira_assignee': None, 'jira_assignee_retrieved_at': '2026-11-15T00:00:00Z'})
        self.assertEqual('2026-01-01T00:00:00Z', issue['updated_at'])
        self.assertEqual('2026-01-02T00:00:00Z', issue['delivery']['freshness']['jira'])

    def test_contradictory_same_task_owner_session_is_execution_conflict_only(self):
        self.put('tasks/p/T.json', {'id': 'T', 'status': 'pending', 'owner': 'worker-one', 'owner_session_id': 'worker-two'})
        o = self.roles({'task_ids': ['T'], 'implementation_owner': 'Implementation project', 'jira_assignee': {'accountId': 'one'}})
        self.assertEqual('conflict', o['execution']['status'])
        self.assertEqual('assigned', o['implementation']['status'])
        self.assertEqual('assigned', o['jira']['status'])

    def test_null_legacy_task_owner_does_not_hide_session_assignment(self):
        self.put('tasks/p/T.json', {'id': 'T', 'status': 'pending', 'owner': None, 'owner_session_id': 'actual-session'})
        o = self.roles({'task_ids': ['T']})
        self.assertEqual('assigned', o['execution']['status'])
        self.assertEqual('actual-session', o['execution']['members'][0]['identity'])

    def test_named_execution_owner_stable_identity_matches_session(self):
        self.put('tasks/p/T.json', {'id': 'T', 'status': 'in_progress',
            'owner': {'displayName': 'Worker display name', 'session_id': 'stable-session'}, 'owner_session_id': 'stable-session'})
        o = self.roles({'task_ids': ['T']})
        self.assertEqual('assigned', o['execution']['status'])
        self.assertEqual('Worker display name', o['execution']['members'][0]['name'])
        self.assertEqual('stable-session', o['execution']['members'][0]['identity'])
        self.assertEqual('in_progress', o['execution']['members'][0]['task_status'])

    def test_repeated_same_worker_preserves_each_task_association(self):
        for task in ('T1', 'T2'):
            self.put('tasks/p/'+task+'.json', {'id': task, 'status': 'pending', 'owner_session_id': 'one-worker'})
        o = self.roles({'task_ids': ['T1', 'T2']})
        self.assertEqual('assigned', o['execution']['status'])
        self.assertEqual({'T1', 'T2'}, {m['task_id'] for m in o['execution']['members']})
        self.assertEqual({'one-worker'}, {m['identity'] for m in o['execution']['members']})

    def test_duplicate_task_identity_with_conflicting_workers_is_ambiguous(self):
        self.put('tasks/p/T.json', {'id': 'T', 'status': 'pending', 'owner_session_id': 'worker-one'})
        self.put('tasks/q/T.json', {'id': 'T', 'status': 'pending', 'owner_session_id': 'worker-two'})
        o = self.roles({'task_ids': ['T']})
        self.assertEqual('conflict', o['execution']['status'])
        self.assertEqual({'worker-one', 'worker-two'}, {m['identity'] for m in o['execution']['members']})

    def test_malformed_execution_and_implementation_records_have_role_local_conflict(self):
        for owner, session in (({}, None), (42, None), (None, [])):
            with self.subTest(owner=owner, session=session):
                self.put('tasks/p/T.json', {'id': 'T', 'status': 'pending', 'owner': owner, 'owner_session_id': session})
                o = self.roles({'task_ids': ['T'], 'implementation_owner': 'Project'})
                self.assertEqual('conflict', o['execution']['status'])
                self.assertEqual('assigned', o['implementation']['status'])
        for value in ('', {}, 42):
            with self.subTest(implementation_owner=value):
                o = self.roles({'implementation_owner': value, 'jira_assignee': {'accountId': 'one'}})
                self.assertEqual('conflict', o['implementation']['status'])
                self.assertEqual('assigned', o['jira']['status'])

    def test_jira_duplicate_read_provenance_kept_for_every_observation(self):
        data = self.duplicate({'jira_assignee': {'accountId': 'stable', 'displayName': 'Old name'},
                              'jira_assignee_source': 'read one', 'jira_assignee_retrieved_at': '2026-01-01T00:00:00Z'},
                             {'jira_assignee': {'accountId': 'stable', 'displayName': 'New name'},
                              'jira_assignee_source': 'read two', 'jira_assignee_retrieved_at': '2026-02-01T00:00:00Z'})
        o = data['issues'][0]['delivery']['ownership']['jira']
        self.assertEqual('assigned', o['status'])
        self.assertEqual({'read one', 'read two'}, {m['source'] for m in o['observations']})
        self.assertEqual({'2026-01-01T00:00:00Z', '2026-02-01T00:00:00Z'}, {m['retrieved_at'] for m in o['observations']})
