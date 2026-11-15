"""Local execution records retain their identity separately from Jira scope."""
import server
from test_server import Fixture


class GraphIdentityTests(Fixture):
    def test_local_task_identity_and_scope_are_not_jira_identity(self):
        self.epic('E', ['A', 'B'], True, [
            {'key': 'A', 'issue_type': 'Story', 'source_status': 'In Progress'},
            {'key': 'B', 'issue_type': 'Development Sub-Task', 'parent_key': 'A'}])
        self.put('epics/E/scope.json', {'epic_key': 'E', 'issue_keys': ['A', 'B'],
                                      'source_issue_type': 'Feature', 'source_status': 'In Progress'})
        self.put('tasks/p/T1.json', {'id': 'T1', 'title': 'E local design', 'issue_key': 'E'})
        self.put('tasks/p/T2.json', {'id': 'T2', 'title': 'A local implementation', 'issue_key': 'A'})
        data = server.build_dashboard(self.root)
        nodes = {node['id']: node for node in data['graph']['nodes']}
        self.assertEqual('Feature', nodes['epic:E']['issue_type'])
        self.assertEqual('In Progress', nodes['epic:E']['source_status'])
        self.assertEqual('Story', nodes['issue:A']['issue_type'])
        self.assertEqual('In Progress', nodes['issue:A']['source_status'])
        self.assertEqual('Development Sub-Task', nodes['issue:B']['issue_type'])
        self.assertEqual('epic', nodes['task:T1']['mapping_kind'])
        self.assertEqual([], nodes['task:T1']['issue_keys'])
        self.assertEqual(['E'], nodes['task:T1']['epic_keys'])
        self.assertEqual('issue', nodes['task:T2']['mapping_kind'])
        self.assertEqual(['A'], nodes['task:T2']['issue_keys'])
        self.assertEqual('E local design', nodes['task:T1']['label'])
        self.assertEqual({'A', 'B'}, {issue['key'] for issue in data['issues']})
