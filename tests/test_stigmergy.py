"""Behavioral checks; made by jared castorena 1728studios llc."""
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

KIT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('stigmergy', KIT / 'tools' / 'stigmergy.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        s.init_workspace(self.root)
        self.base = self.root / '.stigmergy'

    def tearDown(self):
        self.temp.cleanup()

    def memory(self):
        return (self.base / s.MEMORY).read_bytes()

    def post(self, body='An actionable result.', **kwargs):
        args = dict(author='owner', to='worker', kind='assignment', title='A task', body=body, next_owner='worker')
        args.update(kwargs)
        return s.post_mail(self.root, **args)['id']

    def add(self):
        return s.change_goal(self.root, 0, 'goal-1', objective='Build a reusable importer', owner='owner', acceptance=['Valid input imports without loss', 'Invalid input is explained'], next_action='Inspect the contract')

    def test_init_is_private_and_never_overwrites_existing_state(self):
        before = self.memory()
        self.assertEqual((self.base / '.gitignore').read_text(), '*\n')
        with self.assertRaises(FileExistsError):
            s.init_workspace(self.root)
        self.assertEqual(self.memory(), before)
        self.assertEqual(s.workspace_status(self.root)['goal_revision'], 0)

    def test_checkpoint_preserves_complete_old_bytes_with_valid_topic_addresses(self):
        old = self.memory()
        result = s.checkpoint(self.root, b'# Current\n\nVerified change.\n', s.digest(old))
        archive = self.base / result['archive']
        self.assertEqual(archive.read_bytes(), old)
        self.assertEqual(s.digest(archive.read_bytes()), s.digest(old))
        self.assertFalse(archive.stat().st_mode & 0o222)
        index = json.loads((self.base / result['index']).read_text())
        lines = old.decode().splitlines()
        for topic in index['topics']:
            self.assertEqual(re.sub(r'^#+\s+', '', lines[topic['start_line']-1]), topic['title'])
            self.assertLessEqual(topic['end_line'], len(lines))
        self.assertIn(result['archive'], self.memory().decode())

    def test_stale_memory_and_unchanged_body_do_not_write(self):
        old = self.memory()
        with self.assertRaisesRegex(ValueError, 'stale'):
            s.checkpoint(self.root, b'New state', '0'*64)
        self.assertEqual(self.memory(), old)
        self.assertFalse(s.checkpoint(self.root, old, s.digest(old))['changed'])
        self.assertEqual(list((self.base / 'archives').iterdir()), [])

    def test_memory_ceiling_is_checked_before_archiving_and_includes_footer(self):
        old = self.memory()
        for draft in [b'x'*12200, b'x\n'*79]:
            with self.assertRaisesRegex(ValueError, 'final memory exceeds'):
                s.checkpoint(self.root, draft, s.digest(old))
        self.assertEqual(self.memory(), old)
        self.assertEqual(list((self.base / 'archives').iterdir()), [])

    def test_inline_footer_example_is_not_treated_as_a_footer(self):
        draft = b'# Notes\nThe marker <!-- stigmergy:previous-memory --> is discussed here.\nKeep this sentence.\n'
        s.checkpoint(self.root, draft, s.digest(self.memory()))
        self.assertIn(b'Keep this sentence.', self.memory())

    def test_multiple_checkpoints_form_complete_recoverable_history(self):
        original = self.memory()
        first = s.checkpoint(self.root, b'# First\nOne result.\n', s.digest(original))
        intermediate = self.memory()
        second = s.checkpoint(self.root, b'# Second\nAnother result.\n', s.digest(intermediate))
        self.assertEqual((self.base / first['archive']).read_bytes(), original)
        self.assertEqual((self.base / second['archive']).read_bytes(), intermediate)
        unchanged = s.checkpoint(self.root, self.memory(), s.digest(self.memory()))
        self.assertFalse(unchanged['changed'])

    def test_write_failure_keeps_current_memory_and_preserved_archive(self):
        old = self.memory()
        original_write = s.atomic_write
        def fail_current(path, raw, mode=0o600):
            if path.name == s.MEMORY:
                raise OSError('simulated replace failure')
            return original_write(path, raw, mode)
        with patch.object(s, 'atomic_write', side_effect=fail_current):
            with self.assertRaises(OSError):
                s.checkpoint(self.root, b'# New\nPending result.\n', s.digest(old))
        self.assertEqual(self.memory(), old)
        self.assertEqual((self.base / 'archives' / f'memory-{s.digest(old)}.md').read_bytes(), old)
        self.assertFalse((self.base / '.write.lock').exists())

    def test_existing_bad_or_writable_archive_is_not_overwritten(self):
        old = self.memory()
        path = self.base / 'archives' / f'memory-{s.digest(old)}.md'
        for data in [b'wrong bytes', old]:
            path.write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'archive differs or is writable'):
                s.checkpoint(self.root, b'# New\nDifferent.\n', s.digest(old))
            self.assertEqual(self.memory(), old)
            self.assertEqual(path.read_bytes(), data)
            path.unlink()

    def test_writer_lock_refuses_overlap_and_never_breaks_existing_lock(self):
        with s.writer(self.root):
            raw = (self.base / '.write.lock').read_bytes()
            with self.assertRaisesRegex(ValueError, 'writer lock exists'):
                self.add()
            self.assertEqual((self.base / '.write.lock').read_bytes(), raw)
        self.assertFalse((self.base / '.write.lock').exists())

    def test_managed_symlinks_are_rejected(self):
        target = self.root / 'outside.md'
        target.write_text('untouched')
        memory = self.base / s.MEMORY
        memory.unlink(); memory.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            s.checkpoint(self.root, b'Replacement', s.digest(b'untouched'))
        self.assertEqual(target.read_text(), 'untouched')
        archives = self.base / 'archives'
        archives.rmdir(); archives.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            s.managed(self.root, 'archives', 'anything')

    def test_goal_revision_guards_and_archives_prior_state(self):
        old = (self.base / 'goals.json').read_bytes()
        result = self.add()
        self.assertEqual(result['revision'], 1)
        self.assertEqual((self.base / 'archives' / f'goals-{s.digest(old)}.json').read_bytes(), old)
        with self.assertRaisesRegex(ValueError, 'stale'):
            s.change_goal(self.root, 0, 'goal-1', status='blocked', reason='Missing input')
        self.assertEqual(s.read_goals(self.root)['revision'], 1)
        with self.assertRaisesRegex(ValueError, 'no goal update'):
            s.change_goal(self.root, 1, 'goal-1')

    def test_goal_listing_is_bounded_and_exact_reads_include_acceptance(self):
        self.add()
        s.change_goal(self.root, 1, 'goal-2', objective='Review the import result', owner='reviewer', acceptance=['Result matches the input contract'], next_action='Read evidence')
        page = s.list_goals(self.root, limit=1)
        self.assertTrue(page['more'])
        self.assertNotIn('acceptance', page['goals'][0])
        self.assertEqual(s.list_goals(self.root, after=page['next_after'])['goals'][0]['id'], 'goal-2')
        exact = s.exact_goal(self.root, 'goal-1')
        self.assertEqual(exact['revision'], 2)
        self.assertEqual(len(exact['goal']['acceptance']), 2)
        with self.assertRaises(ValueError):
            s.list_goals(self.root, after='unknown')

    def test_goal_completion_requires_review_and_evidence_and_can_reopen(self):
        self.add()
        for changes in [dict(status='completed'), dict(status='completed', reviewed=True), dict(status='completed', evidence=['result.md'])]:
            with self.assertRaisesRegex(ValueError, 'completion requires'):
                s.change_goal(self.root, 1, 'goal-1', **changes)
        result = s.change_goal(self.root, 1, 'goal-1', status='completed', reviewed=True, evidence=['result.md'])
        self.assertTrue(result['goal']['acceptance_reviewed'])
        self.assertEqual(s.read_goals(self.root)['goals'][0]['status'], 'completed')
        reopened = s.change_goal(self.root, 2, 'goal-1', status='active', next_action='Review new requirement')
        self.assertFalse(reopened['goal']['acceptance_reviewed'])

    def test_goal_blocked_or_paused_requires_reason(self):
        self.add()
        for status in ['blocked', 'paused']:
            with self.assertRaises(ValueError):
                s.change_goal(self.root, 1, 'goal-1', status=status)
        result = s.change_goal(self.root, 1, 'goal-1', status='blocked', reason='Input owner must supply the format')
        self.assertEqual(result['goal']['reason'], 'Input owner must supply the format')

    def test_mail_cursors_remain_stable_across_new_appends(self):
        first = self.post()
        second = self.post('A response', kind='completion', reply_to=first)
        page = s.list_mail(self.root, limit=1)
        self.assertEqual(page['next_after'], first)
        third = self.post('Another independent task')
        self.assertEqual([m['id'] for m in s.list_mail(self.root, after=first)['messages']], [second, third])
        self.assertNotIn('body', page['messages'][0])
        with self.assertRaisesRegex(ValueError, 'cursor ID is missing'):
            s.list_mail(self.root, after='unknown')

    def test_exact_mail_reads_use_unicode_offsets_and_are_unverified(self):
        body = 'A unicode handoff: 🌱 café, next owner.'
        ident = self.post(body)
        one = s.exact_mail(self.root, ident, max_chars=21)
        two = s.exact_mail(self.root, ident, offset=one['next_offset'])
        self.assertEqual(one['body'] + two['body'], body)
        self.assertTrue(two['complete'])
        self.assertEqual(one['authentication'], 'unverified')

    def test_mail_detects_body_edits_and_duplicate_ids_without_returning_body(self):
        self.post('original content')
        path = self.base / s.MAIL
        original = path.read_text()
        path.write_text(original.replace('original content', 'changed content'))
        with self.assertRaisesRegex(ValueError, 'checksum'):
            s.list_mail(self.root)
        path.write_text(original + s.MESSAGE.search(original)[0])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            s.list_mail(self.root)

    def test_mail_checks_do_not_authenticate_claimed_author(self):
        ident = self.post()
        path = self.base / s.MAIL
        path.write_text(path.read_text().replace('"author": "owner"', '"author": "different-claim"'))
        result = s.exact_mail(self.root, ident)
        self.assertEqual(result['metadata']['author'], 'different-claim')
        self.assertEqual(result['authentication'], 'unverified')

    def test_bad_replies_delimiters_and_oversize_mail_never_append(self):
        old = (self.base / s.MAIL).read_bytes()
        for body, fields in [('body', {'reply_to': 'missing'}), ('<!-- /stigmergy-message -->', {}), ('x'*4001, {})]:
            with self.assertRaises(ValueError):
                self.post(body, **fields)
        self.assertEqual((self.base / s.MAIL).read_bytes(), old)

    def test_cli_outputs_json_and_returns_nonzero_for_conflicts(self):
        script = KIT / 'tools' / 'stigmergy.py'
        result = subprocess.run([sys.executable, str(script), '--root', str(self.root), 'status'],capture_output=True,text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['goal_revision'], 0)
        result = subprocess.run([sys.executable, str(script), '--root', str(self.root), 'mail', 'read', 'missing'],capture_output=True,text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('error', json.loads(result.stderr))

    @unittest.skipUnless(shutil.which('git'), 'Git is optional for the helper')
    def test_initialized_records_are_ignored_by_a_future_git_repository(self):
        subprocess.run(['git','init','-q',str(self.root)],check=True,capture_output=True)
        (self.root / 'public.md').write_text('public')
        status = subprocess.check_output(['git','-C',str(self.root),'status','--porcelain','--untracked-files=all'],text=True)
        self.assertIn('public.md',status)
        self.assertNotIn('.stigmergy',status)


class DistributionTests(unittest.TestCase):
    def test_manifest_and_markdown_references_resolve(self):
        manifest = json.loads((KIT / 'agent-manifest.json').read_text())
        for path in [*manifest['entrypoints'].values(),manifest['templates'],manifest['helper']]:
            self.assertTrue((KIT / path).exists(), path)
        for path in [*KIT.glob('*.md'),*KIT.glob('docs/*.md')]:
            for target in re.findall(r'\]\(([^)]+)\)', path.read_text()):
                if '://' not in target and not target.startswith('#'):
                    self.assertTrue((path.parent / target.split('#')[0]).exists(), (path.name,target))

    def test_requested_credit_and_no_formal_license(self):
        for name in ['README.md','AGENTS.md','ATTRIBUTION.md','stigmergicmemory.md','stigmergichat.md','PROTOCOL.md']:
            self.assertIn(s.CREDIT, (KIT / name).read_text())
        self.assertIsNone(json.loads((KIT / 'agent-manifest.json').read_text())['formal_license'])
        self.assertFalse(list(KIT.glob('LICENSE*')))


if __name__ == '__main__':
    unittest.main()
