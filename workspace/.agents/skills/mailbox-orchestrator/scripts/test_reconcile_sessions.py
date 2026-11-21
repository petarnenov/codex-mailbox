import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from reconcile_sessions import main

OLD, NEW, OTHER = 'old-session', 'new-session', 'other-session'


class ReconcileSessionsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.register(OLD, 'proj')
        self.lock = self.task('t1', OLD)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return path

    def register(self, session_id, project):
        return self.write(f'sessions/{project}--{session_id}.json',
                          {'role': 'worker', 'project': project, 'session_id': session_id})

    def task(self, task_id, owner, **fields):
        self.write(f'tasks/proj/{task_id}.json', {'id': task_id, 'status': 'in_progress', **fields})
        return self.write(f'tasks/proj/{task_id}.lock/owner.json', {'owner_session_id': owner}).parent

    def run_command(self, *args):
        return main(['--root', str(self.root), *args])

    def test_inventory_lists_locks_and_unread_messages_and_requires_a_probe(self):
        self.write('inbox/proj/m1.json', {'id': 'm1', 'intended_endpoint': OLD})
        self.write('inbox/proj/m2.json', {'id': 'm2', 'intended_endpoint': OTHER})
        (entry,) = self.run_command('inventory')
        self.assertEqual(entry['locks'], ['tasks/proj/t1.lock'])
        self.assertEqual(entry['unread_messages'], ['inbox/proj/m1.json'])
        self.assertEqual(entry['liveness'], 'probe required')

    def test_inventory_flags_a_registration_without_project_instead_of_failing(self):
        self.write('sessions/x--broken.json', {'role': 'worker', 'session_id': 'broken'})
        broken = next(e for e in self.run_command('inventory') if e['session_id'] == 'broken')
        self.assertEqual(broken['liveness'], 'malformed registration')

    def test_retire_archives_registration_and_messages_and_orphans_tasks_without_releasing_locks(self):
        self.write('inbox/proj/m1.json', {'id': 'm1', 'to_endpoint': OLD})
        result = self.run_command('retire', '--session', OLD, '--evidence', 'not listed; PING unanswered 60s')
        self.assertFalse((self.root / 'sessions/proj--old-session.json').exists())
        self.assertTrue((self.root / 'archive/sessions-removed/proj--old-session.json').exists())
        self.assertTrue((self.root / 'archive/proj/m1.json').exists())
        self.assertTrue((self.lock / 'owner.json').exists())
        orphan = json.loads((self.root / 'orphans/t1.json').read_text())
        self.assertEqual(orphan['previous_owner'], {'owner_session_id': OLD})
        self.assertEqual(result['orphaned_tasks'], ['t1'])
        self.assertTrue(list((self.root / 'decisions/sessions').glob('*.json')))

    def test_retire_reports_uncommitted_changes_in_a_named_worktree(self):
        worktree = self.root / 'wt'
        worktree.mkdir()
        subprocess.run(['git', 'init', '-q', str(worktree)], check=True)
        (worktree / 'dirty.txt').write_text('x')
        self.task('t1', OLD, evidence=[f'implementation in {worktree}'])
        self.run_command('retire', '--session', OLD, '--evidence', 'unreachable')
        orphan = json.loads((self.root / 'orphans/t1.json').read_text())
        self.assertEqual(orphan['worktrees'], [{'path': str(worktree), 'uncommitted_changes': 1}])

    def test_retire_refuses_empty_evidence_or_an_unknown_session(self):
        with self.assertRaisesRegex(ValueError, 'evidence'):
            self.run_command('retire', '--session', OLD, '--evidence', ' ')
        with self.assertRaisesRegex(ValueError, 'found 0'):
            self.run_command('retire', '--session', 'ghost', '--evidence', 'x')

    def test_takeover_moves_the_lock_with_succession_and_clears_the_orphan(self):
        self.run_command('retire', '--session', OLD, '--evidence', 'unreachable')
        self.register(NEW, 'proj')
        result = self.run_command('takeover', '--task', 't1', '--to', NEW, '--evidence', 'worktree clean, continuing T3')
        owner = json.loads((self.lock / 'owner.json').read_text())
        self.assertEqual(owner['owner_session_id'], NEW)
        self.assertEqual(owner['succession'][0]['from'], OLD)
        self.assertEqual(result['succession'][0]['to'], NEW)
        self.assertFalse((self.root / 'orphans/t1.json').exists())
        self.assertTrue((self.root / 'archive/orphans-resolved/t1.json').exists())

    def test_takeover_refuses_unorphaned_tasks_other_projects_and_a_returned_owner(self):
        self.register(NEW, 'proj')
        with self.assertRaisesRegex(ValueError, 'not orphaned'):
            self.run_command('takeover', '--task', 't1', '--to', NEW, '--evidence', 'x')
        self.run_command('retire', '--session', OLD, '--evidence', 'unreachable')
        self.register(OTHER, 'elsewhere')
        with self.assertRaisesRegex(ValueError, 'not proj'):
            self.run_command('takeover', '--task', 't1', '--to', OTHER, '--evidence', 'x')
        self.register(OLD, 'proj')
        with self.assertRaisesRegex(ValueError, 'registered again'):
            self.run_command('takeover', '--task', 't1', '--to', NEW, '--evidence', 'x')


if __name__ == '__main__':
    unittest.main()
