"""Graph regressions: hierarchy is distinct from evidence-backed prerequisites."""
import server
from test_server import Fixture


class DependencyTests(Fixture):
    def graph(self):
        data = server.build_dashboard(self.root)
        return data, {n['id']: n for n in data['graph']['nodes']}, data['graph']['edges']

    def spec(self, nodes=None, edges=None):
        self.put('epics/E/dependencies.json', {'nodes': nodes or [], 'edges': edges or []})

    def test_immediate_parents_and_task_membership(self):
        self.epic('E', ['A', 'B'], True, [{'key': 'A', 'projects': ['p']},
                                       {'key': 'B', 'parent': {'key': 'A'}}])
        self.put('tasks/p/T.json', {'id': 'T', 'issue_key': 'B'})
        self.put('tasks/p/U.json', {'id': 'U'})
        self.put('tasks/p/V.json', {'id': 'V', 'issue_key': 'E'})
        _, nodes, edges = self.graph()
        pairs = {(e['from'], e['to']) for e in edges if e['kind'] == 'membership'}
        self.assertIn(('epic:E', 'issue:A'), pairs)
        self.assertIn(('issue:A', 'issue:B'), pairs)
        self.assertNotIn(('epic:E', 'issue:B'), pairs)
        self.assertIn(('issue:B', 'task:T'), pairs)
        self.assertIn(('project:p', 'task:U'), pairs)
        self.assertIn(('epic:E', 'task:V'), pairs)
        self.assertFalse(nodes['issue:A']['ready'])

    def test_blocks_directions_and_reciprocal_deduplication(self):
        self.epic('E', ['A', 'B'], True, [
            {'key': 'A', 'jira_links': [{'type': 'Blocks', 'outward': 'B'},
                                       {'type': 'Relates', 'outward': 'OTHER'}]},
            {'key': 'B', 'issuelinks': [{'type': {'name': 'Blocks'}, 'inwardIssue': {'key': 'A'}},
                                      {'type': {'name': 'Work item split'}, 'outwardIssue': {'key': 'SPLIT'}}]}])
        _, _, edges = self.graph()
        self.assertEqual([('issue:A', 'issue:B')], [(e['from'], e['to']) for e in edges if e['kind'] == 'requires'])

    def test_external_outward_is_downstream_and_unknown_has_no_arrow(self):
        self.epic('E', [], True, [], external_dependencies=[
            {'key': 'OUT', 'relationship': {'name': 'Blocks'}, 'direction': 'outward'},
            {'key': 'IN', 'relationship': {'name': 'Blocks'}, 'direction': 'inward'}, 'UNKNOWN'])
        data, nodes, edges = self.graph()
        pairs = {(e['from'], e['to']) for e in edges if e['kind'] == 'requires'}
        self.assertEqual({('epic:E', 'issue:OUT'), ('issue:IN', 'epic:E')}, pairs)
        self.assertTrue(nodes['issue:UNKNOWN']['unresolved'])
        self.assertIn('direction unknown', nodes['issue:UNKNOWN']['status'])
        self.assertEqual('outward', data['external_dependencies'][0]['direction'])

    def test_milestone_readiness_is_explicit_and_does_not_promote_issue(self):
        self.epic('E', ['A'], True, [{'key': 'A', 'source_status': 'Closed'}])
        self.spec([{'id': 'milestone:M', 'label': 'Published', 'status': 'verified',
                    'verification': 'passed', 'evidence': ['proof'], 'projects': ['p'], 'teams': ['BE']}],
                  [{'from': 'milestone:M', 'to': 'issue:A', 'kind': 'requires', 'condition': 'Exact artifact', 'evidence': ['decision']}])
        data, nodes, edges = self.graph()
        self.assertTrue(nodes['milestone:M']['ready'])
        self.assertFalse(nodes['issue:A']['ready'])
        self.assertEqual([], nodes['issue:A']['unmet_prerequisites'])
        self.assertEqual(0, data['totals']['verified_issues'])
        self.assertEqual(['E'], nodes['milestone:M']['epic_keys'])
        self.assertEqual('Exact artifact', next(e for e in edges if e['kind'] == 'requires')['condition'])

    def test_missing_evidence_unknown_nodes_and_cycles_are_unmet(self):
        self.epic('E', ['A', 'B'], True, [{'key': 'A', 'depends_on': ['B']}, {'key': 'B', 'depends_on': ['A']}])
        self.spec([{'id': 'milestone:M', 'status': 'verified', 'verification': 'passed'}],
                  [{'from': 'milestone:M', 'to': 'task:absent', 'kind': 'requires', 'evidence': ['decision']}])
        _, nodes, _ = self.graph()
        self.assertFalse(nodes['milestone:M']['ready'])
        self.assertEqual(['issue:B'], nodes['issue:A']['unmet_prerequisites'])
        self.assertTrue(nodes['task:absent']['unresolved'])
        self.assertEqual(['milestone:M'], nodes['task:absent']['unmet_prerequisites'])

    def test_task_requires_completion_evidence(self):
        self.epic('E', [], True, [])
        for key, extra in [('A', {'evidence': ['proof']}), ('B', {})]:
            self.put(f'tasks/p/{key}.json', {'id': key, 'status': 'done', **extra})
        self.put('tasks/p/C.json', {'id': 'C', 'depends_on': ['B', 'A']})
        _, nodes, _ = self.graph()
        self.assertTrue(nodes['task:A']['ready'])
        self.assertEqual(['proof'], nodes['task:A']['evidence'])
        self.assertFalse(nodes['task:B']['ready'])
        self.assertEqual(['task:B'], nodes['task:C']['unmet_prerequisites'])

    def test_structured_native_evidence_preserved_and_numeric_claim_not_ready(self):
        self.epic('E', [], True, [])
        self.put('tasks/p/T.json', {'id': 'T', 'status': 'done', 'evidence': [{'report': 'report.json', 'results': ['PASS', 42]}]})
        self.put('tasks/p/N.json', {'id': 'N', 'status': 'done', 'evidence': 42})
        _, nodes, _ = self.graph()
        self.assertEqual(['PASS', 'report.json'], nodes['task:T']['evidence'])
        self.assertTrue(nodes['task:T']['ready'])
        self.assertFalse(nodes['task:N']['ready'])

    def test_milestone_blank_evidence_never_means_verified(self):
        self.epic('E', [], True, [])
        self.spec([
            {'id': 'milestone:empty', 'status': 'verified', 'verification': 'passed', 'evidence': ['']},
            {'id': 'milestone:spaces', 'status': 'verified', 'verification': 'passed', 'evidence': ['  ', '\t\n']},
            {'id': 'milestone:valid', 'status': 'verified', 'verification': 'passed', 'evidence': ['', '  proof.json  ', '\t']},
        ])
        _, nodes, _ = self.graph()
        for key in ('milestone:empty', 'milestone:spaces'):
            self.assertFalse(nodes[key]['ready'])
            self.assertEqual('unknown', nodes[key]['status'])
            self.assertEqual([], nodes[key]['evidence'])
        self.assertTrue(nodes['milestone:valid']['ready'])
        self.assertEqual(['proof.json'], nodes['milestone:valid']['evidence'])

    def test_invalid_graph_records_warn_without_crashing(self):
        self.epic('E', ['A'], True, [{'key': 'A'}])
        self.put('epics/E/dependencies.json', {'nodes': [None, {'id': []}, {'id': 'issue:A'},
             {'id': 'milestone:bad', 'projects': [{}]}, {'id': 'milestone:badteam', 'teams': 3}],
             'edges': [None, {'from': [], 'to': 'issue:A'}, {'from': 'x', 'to': 'issue:A', 'kind': 'requires'},
                       {'from': 'issue:A', 'to': 'task:T', 'kind': 'relates'}]})
        data, nodes, _ = self.graph()
        self.assertNotIn('milestone:bad', nodes)
        self.assertFalse(nodes['issue:A']['ready'])
        self.assertTrue(data['warnings'])

    def test_conflicting_milestones_and_parents_fail_closed(self):
        self.epic('E', ['A'], True, [{'key': 'A', 'parent_key': 'P', 'local_status': 'verified_done', 'verification': 'passed', 'evidence': ['proof']},
                                       {'key': 'A', 'parent_key': 'Q', 'local_status': 'verified_done', 'verification': 'passed', 'evidence': ['proof']}])
        self.spec([{'id': 'milestone:M', 'status': 'verified', 'verification': 'passed', 'evidence': ['proof']},
                   {'id': 'milestone:M', 'status': 'unknown'}])
        data, nodes, _ = self.graph()
        self.assertFalse(nodes['milestone:M']['ready'])
        self.assertFalse(nodes['issue:A']['ready'])
        self.assertTrue(any('conflicting parent' in w for w in data['warnings']))

    def test_malformed_spec_collections_and_raw_links(self):
        self.epic('E', ['A'], True, [{'key': 'A', 'parent': [], 'jira_links': [None, {'type': [], 'inward': []}]}])
        self.put('epics/E/dependencies.json', {'nodes': {}, 'edges': 'bad'})
        data, nodes, _ = self.graph()
        self.assertIn('issue:A', nodes)
        self.assertTrue(data['warnings'])

    def test_issue_evidence_and_missing_parent_endpoint(self):
        self.epic('E', ['A'], True, [{'key': 'A', 'parent_key': 'missing', 'local_status': 'verified_done',
            'verification': 'passed', 'evidence': ['acceptance proof'], 'updated_at': '2026-11-15T00:00:00Z'}])
        _, nodes, edges = self.graph()
        self.assertTrue(nodes['issue:A']['ready'])
        self.assertEqual(['acceptance proof'], nodes['issue:A']['evidence'])
        self.assertEqual('2026-11-15T00:00:00Z', nodes['issue:A']['updated_at'])
        self.assertTrue(nodes['issue:missing']['unresolved'])
        self.assertTrue(next(e for e in edges if e['to'] == 'issue:A')['unresolved'])

    def test_invalid_json_and_nonlist_relationships_are_isolated(self):
        self.epic('E', ['A'], True, [{'key': 'A', 'jira_links': 42}])
        self.put('epics/E/dependencies.json', [])
        data, _, _ = self.graph()
        self.assertTrue(any('invalid Jira relationship list' in w for w in data['warnings']))
        self.assertTrue(any('invalid dependency graph' in w for w in data['warnings']))

    def test_identical_shared_milestone_unions_epic_membership(self):
        self.epic('E', [], True, [])
        self.epic('F', [], True, [])
        record = {'id': 'milestone:M', 'label': 'shared', 'status': 'verified', 'verification': 'passed', 'evidence': ['x']}
        self.spec([record])
        self.put('epics/F/dependencies.json', {'nodes': [record]})
        _, nodes, _ = self.graph()
        self.assertTrue(nodes['milestone:M']['ready'])
        self.assertEqual(['E', 'F'], nodes['milestone:M']['epic_keys'])

    def test_invalid_label_status_and_edge_metadata_are_skipped(self):
        self.epic('E', [], True, [])
        self.spec([{'id': 'milestone:M', 'label': []}, {'id': 'milestone:N', 'status': []}],
            [{'from': 'epic:E', 'to': 'issue:X', 'kind': 'requires', 'evidence': [{}]},
             {'from': 'epic:E', 'to': 'issue:X', 'kind': 'requires', 'condition': []}])
        data, nodes, edges = self.graph()
        self.assertNotIn('milestone:M', nodes)
        self.assertFalse(edges)
        self.assertTrue(data['warnings'])
