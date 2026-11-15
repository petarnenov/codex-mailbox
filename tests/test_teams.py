import unittest

import server
from test_server import Fixture


class TeamClassificationTests(unittest.TestCase):
    def test_explicit_aliases_override_title_and_empty_is_unassigned(self):
        self.assertEqual(server.record_teams({'team': 'frontend', 'title': 'Run Tests'}, ['BE']), ['FE'])
        self.assertEqual(server.record_teams({'teams': ['Backend', 'qa', 'FE', 'bad', 3]}, []), ['BE', 'FE', 'QA'])
        self.assertEqual(server.record_teams({'teams': [], 'title': 'UI app'}, ['BE']), [])
        self.assertEqual(server.record_teams({'team': None}, ['BE']), ['BE'])
        self.assertEqual(server.record_teams({'team': 'bad'}, ['BE']), [])

    def test_title_inference_testing_precedence_and_unknown(self):
        for title in ['Test Cases - roles', 'Run Tests - app', 'DEV - Create (dev)Tests',
                      'FE - unit testing', 'UI - integration test', '[QA] roles', 'Quality Assurance - roles']:
            with self.subTest(title=title):
                self.assertEqual(server.record_teams({'title': title}, ['BE']), ['QA'])
        for title in ['UI - roles', 'FE: app', '[FE] app', 'Frontend app', 'front-end app']:
            self.assertEqual(server.record_teams({'summary': title}, []), ['FE'])
        for title in ['DEV - roles', 'BE: roles', 'Backend roles', 'back-end roles', '[BE] roles']:
            self.assertEqual(server.record_teams({'title': title}, []), ['BE'])
        self.assertEqual(server.record_teams({'title': 'Unknown'}, []), [])
        self.assertEqual(server.record_teams({'title': 'Unknown'}, ['BE', 'FE']), ['BE', 'FE'])


class TeamProjectionTests(Fixture):
    def test_ownership_explicit_projects_tasks_sources_and_duplicate_issues(self):
        self.put('projects.json', {'projects': [{'id': 'admin-center'}, {'id': 'frontend'},
                                               {'id': 'custom', 'team': 'qa'}, {'id': 'unknown'}]})
        self.put('projects/custom.json', {'teams': ['FE'], 'statistics': {'count': 1}})
        self.put('epics/E/scope.json', {'epic_key': 'E', 'enumeration_complete': True})
        self.put('epics/E/issues.json', [
            {'key': 'QA-1', 'title': 'DEV - Create tests', 'projects': ['admin-center']},
            {'key': 'UI-1', 'title': 'UI - app', 'projects': ['admin-center']},
            {'key': 'B-1', 'title': 'Unknown', 'projects': ['admin-center']},
            {'key': 'M-1', 'projects': ['frontend', 'admin-center']},
            {'key': 'X-1', 'team': 'BE'}, {'key': 'X-1', 'team': 'FE'},
            {'key': 'U-1', 'projects': ['unknown']},
        ])
        self.put('tasks/admin-center/t.json', {'id': 't', 'issue_key': 'QA-1'})
        self.put('tasks/admin-center/override.json', {'id': 'override', 'issue_key': 'QA-1', 'team': 'FE'})
        self.put('tasks/admin-center/title.json', {'id': 'title', 'title': 'UI - recovery', 'issue_key': 'QA-1'})
        self.put('tasks/admin-center/fallback.json', {'id': 'fallback'})
        self.put('epics/E/progress.json', {'team': 'QA', 'statistics': {'count': 2}})
        result = server.build_dashboard(self.root)
        issues = {i['key']: i['teams'] for i in result['issues']}
        self.assertEqual(issues, {'QA-1': ['QA'], 'UI-1': ['FE'], 'B-1': ['BE'],
                                  'M-1': ['BE', 'FE'], 'X-1': ['BE', 'FE'], 'U-1': []})
        tasks = {t['id']: t['teams'] for t in result['tasks']}
        self.assertEqual(tasks, {'t': ['QA'], 'override': ['FE'], 'title': ['FE'], 'fallback': ['BE']})
        self.assertTrue(all('_inherit_teams' not in t for t in result['tasks']))
        projects = {p['id']: p['teams'] for p in result['projects']}
        self.assertEqual(projects['custom'], ['FE'])
        self.assertEqual(projects['unknown'], [])
        self.assertEqual([r['teams'] for r in result['reported_statistics']], [['FE'], ['QA']])
