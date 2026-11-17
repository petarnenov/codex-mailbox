import json
import tempfile
import unittest
import uuid
from pathlib import Path

from new_task import create_task


class NewTaskTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'mailbox'
        self.repo = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        self.repo.mkdir()
        registry = {'schema_version': 1, 'projects': [{
            'id': 'demo', 'repository_path': str(self.repo), 'working_directory': str(self.repo)}]}
        (self.root / 'projects.json').write_text(json.dumps(registry))

    def tearDown(self):
        self.temp.cleanup()

    def add_loop(self, name, skill_dir='.claude/skills'):
        skill = self.repo / skill_dir / name / 'SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('loop')
        return skill

    def test_creates_task_with_uuid_verbatim_text_and_discovered_loop(self):
        skill = self.add_loop('demo.loop')
        text = 'Fix the login timeout\nKeep the session for 30 minutes.'

        task, path = create_task(self.root, 'demo', text)

        self.assertEqual(str(uuid.UUID(task['id'])), task['id'])
        self.assertEqual(path, self.root / 'tasks' / 'demo' / f"{task['id']}.json")
        self.assertEqual(json.loads(path.read_text()), task)
        self.assertEqual(task['description'], text)
        self.assertEqual(task['title'], 'Fix the login timeout')
        self.assertEqual(task['source'], 'free_text')
        self.assertEqual((task['required_loop_skill'], task['required_loop_path']), ('demo.loop', str(skill.resolve())))
        self.assertEqual(task['blockers'], [])

    def test_each_task_gets_a_distinct_id(self):
        self.add_loop('demo.loop')
        first, _ = create_task(self.root, 'demo', 'one')
        second, _ = create_task(self.root, 'demo', 'two')
        self.assertNotEqual(first['id'], second['id'])

    def test_explicit_title_and_long_first_line(self):
        self.add_loop('demo.loop')
        titled, _ = create_task(self.root, 'demo', 'body', title='Custom')
        long_line, _ = create_task(self.root, 'demo', 'x' * 200)
        self.assertEqual(titled['title'], 'Custom')
        self.assertEqual(len(long_line['title']), 80)

    def test_missing_loop_skill_becomes_blocker(self):
        task, _ = create_task(self.root, 'demo', 'work')
        self.assertIsNone(task['required_loop_skill'])
        self.assertIn('none found', task['blockers'][0])

    def test_ambiguous_loop_skill_becomes_blocker(self):
        self.add_loop('a.loop')
        self.add_loop('b.loop', '.agents/skills')
        task, _ = create_task(self.root, 'demo', 'work')
        self.assertIn('ambiguous: a.loop, b.loop', task['blockers'][0])

    def test_rejects_unknown_project_and_empty_text(self):
        with self.assertRaisesRegex(ValueError, "Unknown project 'other'"):
            create_task(self.root, 'other', 'work')
        with self.assertRaisesRegex(ValueError, 'must not be empty'):
            create_task(self.root, 'demo', '   ')
        self.assertFalse((self.root / 'tasks').exists())


if __name__ == '__main__':
    unittest.main()
