"""Exercise the published agent contract against the actual CLI, without dependencies."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_stigmergy import KIT, s


class AgentInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        s.init_workspace(self.root)

    def cli(self, *argv, expected=0):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = s.main(['--root', str(self.root), *map(str, argv)])
        self.assertEqual(code, expected, err.getvalue())
        if code:
            self.assertEqual(out.getvalue(), '')
            result = json.loads(err.getvalue())
            self.assertFalse(result['ok'])
            self.assertEqual(result['error']['recovery'], s.RECOVERY[result['error']['code']])
        else:
            self.assertEqual(err.getvalue(), '')
            result = json.loads(out.getvalue())
            self.assertTrue(result['ok'])
        self.assertEqual(result['interface_version'], 2)
        return result

    def add(self, ident='task', owner='worker'):
        return s.change_goal(self.root, s.read_goals(self.root)['revision'], ident,
                             objective='Produce an inspected result', owner=owner,
                             acceptance=['Output meets the request'], next_action='Inspect input')

    def post(self, recipient='worker'):
        return s.post_mail(self.root, author='owner', to=recipient, kind='assignment',
                           title='Assigned task', body='SECRET_MAIL_BODY', next_owner=recipient)['id']

    def test_every_published_command_template_executes_and_returns_promised_fields(self):
        contract = json.loads((KIT / 'agent-contract.json').read_text())
        self.root = self.root / 'adopted-project'
        self.root.mkdir()
        draft = self.root / 'draft.md'
        draft.write_text('# State\nGoal reviewed; evidence retained.\n')
        message = self.root / 'body.md'
        message.write_text('Inspect the input and report evidence to the owner.')
        bindings = dict(KIT=str(KIT), ROOT=str(self.root), GOAL_ID='work', OWNER='owner',
                        OBJECTIVE='Produce an inspected artifact', ACCEPTANCE='Artifact matches the request',
                        NEXT_ACTION='Inspect the input', REVISION='0', EVIDENCE='evidence/result.txt',
                        DRAFT_FILE=str(draft), BODY_FILE=str(message), TITLE='Inspect input', RECIPIENT='worker')
        order = ['contract', 'init', 'resume', 'status', 'goal_list', 'goal_add', 'goal_read', 'goal_update',
                 'goal_complete', 'checkpoint', 'mail_post', 'mail_list', 'mail_read']
        self.assertEqual(set(order), set(contract['commands']))
        for name in order:
            command = contract['commands'][name]
            argv = [a.format_map(bindings) for a in contract['invocation']['prefix'] + command['argv']]
            self.assertEqual(argv[0:2], ['python3', str(KIT / 'tools/stigmergy.py')])
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                status = s.main(argv[2:])
            self.assertEqual(status, 0, (name, err.getvalue()))
            result = json.loads(out.getvalue())
            self.assertTrue(result['ok'])
            self.assertLessEqual(set(command['result']), result.keys(), name)
            if 'revision' in result:
                bindings['REVISION'] = str(result['revision'])
            if 'memory_sha256' in result:
                bindings['MEMORY_SHA256'] = result['memory_sha256']
            if name == 'mail_post':
                bindings['MESSAGE_ID'] = result['id']
                self.assertTrue(result['native_delivery_required'])
        self.assertEqual(s.exact_goal(self.root, 'work')['goal']['status'], 'completed')
        self.assertEqual(s.exact_mail(self.root, bindings['MESSAGE_ID'])['body'], message.read_text())

    def test_contract_lookup_needs_no_initialized_state_and_loads_only_one_operation(self):
        self.root = self.root/'not-initialized'
        result = self.cli('contract', '--operation', 'checkpoint')
        self.assertEqual(result['operation'], 'checkpoint')
        self.assertEqual(result['command']['argv'][0], 'checkpoint')
        self.assertEqual(set(result['bindings']), {'KIT', 'ROOT', 'DRAFT_FILE', 'MEMORY_SHA256'})
        self.assertNotIn('loop', result)
        self.assertNotIn('goal_add', json.dumps(result))
        self.assertFalse(self.root.exists())
        self.assertEqual(self.cli('contract', '--operation', 'missing', expected=1)['error']['code'], 'E_NOT_FOUND')

    def test_resume_obeys_serialized_budget_and_continues_unicode_without_history(self):
        old = s.managed(self.root, s.MEMORY).read_bytes()
        s.checkpoint(self.root, ('# Current\n' + '🌱\t' * 1600 + '\n').encode(), s.digest(old))
        complete_memory = s.managed(self.root, s.MEMORY).read_text()
        for i in range(4):
            self.add('g'+str(i), owner='🌱' * 500)
            self.post('🌱' * 500)
        offset, sha, reconstructed = 0, None, ''
        for _ in range(30):
            packet = s.resume(self.root, memory_offset=offset, expected_memory=sha, max_bytes=2048)
            encoded = s.json_bytes(s.success(packet))
            self.assertLessEqual(len(encoded), 2048)
            self.assertNotIn(b'SECRET_MAIL_BODY', encoded)
            self.assertNotIn(b'Output meets the request', encoded)
            self.assertEqual(packet['snapshot'], 'sequential_reads')
            memory = packet['memory']
            reconstructed += memory['body']
            sha = memory['sha256']
            self.assertGreater(memory['next_offset'], offset)
            offset = memory['next_offset']
            if memory['complete']:
                break
        else:
            self.fail('resume continuation did not terminate')
        self.assertEqual(reconstructed, complete_memory)
        process = subprocess.run([sys.executable, str(KIT/'tools/stigmergy.py'), '--root', str(self.root),
                                  'resume', '--max-bytes', '2048'], capture_output=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertLessEqual(len(process.stdout), 2048)
        self.assertEqual(json.loads(process.stdout)['memory']['sha256'], sha)

    def test_trimmed_metadata_retains_cursors_and_dedicated_reads_make_progress(self):
        self.add('g0')
        first = self.post()
        self.add('g1', owner='🌱'*500)
        second = self.post('🌱'*500)
        packet = s.resume(self.root, goal_after='g0', mail_after=first, max_bytes=2048)
        self.assertEqual(packet['goals']['goals'], [])
        self.assertTrue(packet['goals']['more'])
        self.assertEqual(packet['goals']['next_after'], 'g0')
        self.assertEqual(packet['mail']['messages'], [])
        self.assertTrue(packet['mail']['more'])
        self.assertEqual(packet['mail']['next_after'], first)
        self.assertEqual(s.list_goals(self.root, after='g0')['goals'][0]['id'], 'g1')
        self.assertEqual(s.list_mail(self.root, after=first)['messages'][0]['id'], second)

    def test_memory_continuation_requires_the_same_observed_hash(self):
        packet = s.resume(self.root)
        self.assertEqual(self.cli('resume', '--memory-offset', '1', expected=1)['error']['code'], 'E_INVALID_INPUT')
        self.assertEqual(self.cli('resume', '--memory-offset', '1', '--expect-memory-sha256', '0'*64,
                                  expected=1)['error']['code'], 'E_STALE_MEMORY')
        original = packet['memory']['sha256']
        s.checkpoint(self.root, b'# Changed\nA later result.\n', original)
        self.assertEqual(self.cli('resume', '--expect-memory-sha256', original,
                                  expected=1)['error']['code'], 'E_STALE_MEMORY')

    def test_errors_are_stable_and_conflicts_never_require_parsing_diagnostic_text(self):
        self.add()
        draft = self.root / 'draft.md'
        draft.write_text('# New\nPending.\n')
        cases = [
            (['init'], 'E_ALREADY_INITIALIZED', 1),
            (['not-a-command'], 'E_USAGE', 2),
            (['resume', '--limit', 'many'], 'E_USAGE', 2),
            (['resume', '--max-bytes', '1'], 'E_INVALID_INPUT', 1),
            (['checkpoint', '--draft', str(draft), '--expect-sha256', '0'*64], 'E_STALE_MEMORY', 1),
            (['goal', 'update', 'task', '--next-action', 'Inspect output', '--expect-revision', '0'], 'E_STALE_GOAL', 1),
            (['mail', 'list', '--after', 'missing'], 'E_MISSING_CURSOR', 1),
            (['goal', 'read', 'missing'], 'E_NOT_FOUND', 1),
            (['checkpoint', '--draft', str(self.root/'absent'), '--expect-sha256', '0'*64], 'E_IO', 1),
        ]
        for args, code, exit_code in cases:
            self.assertEqual(self.cli(*args, expected=exit_code)['error']['code'], code)
        with s.writer(self.root):
            self.assertEqual(self.cli('goal', 'update', 'task', '--next-action', 'Inspect output',
                                     '--expect-revision', '1', expected=1)['error']['code'], 'E_LOCKED')
        self.root = self.root/'uninitialized'
        self.root.mkdir()
        self.assertEqual(self.cli('resume', expected=1)['error']['code'], 'E_NOT_INITIALIZED')

    def test_corrupted_persisted_records_are_distinguished_from_bad_inputs(self):
        self.post()
        mail = s.managed(self.root, s.MAIL)
        mail.write_text(mail.read_text().replace('SECRET_MAIL_BODY', 'CORRUPT_BODY_MUST_NOT_PRINT'))
        result = self.cli('resume', expected=1)
        self.assertEqual(result['error']['code'], 'E_MAIL_INTEGRITY')
        self.assertNotIn('CORRUPT_BODY_MUST_NOT_PRINT', json.dumps(result))
        self.add()
        goals = s.managed(self.root, 'goals.json')
        value = json.loads(goals.read_text())
        for field, invalid in [('schema_version', True), ('goals', [{'id': 12}])]:
            bad = {**value, field: invalid}
            goals.write_text(json.dumps(bad))
            self.assertEqual(self.cli('goal', 'list', expected=1)['error']['code'], 'E_GOAL_INTEGRITY')

    def test_schema_contract_versions_codes_and_generated_record_fields_agree(self):
        contract = json.loads((KIT/'agent-contract.json').read_text())
        manifest = json.loads((KIT/'agent-manifest.json').read_text())
        schema = json.loads((KIT/'schemas/records.schema.json').read_text())['$defs']
        self.assertEqual(manifest['version'], contract['kit_version'])
        self.assertEqual(manifest['interface_version'], s.INTERFACE_VERSION)
        self.assertEqual(contract['recovery'], s.RECOVERY)
        self.assertEqual(set(schema['error']['properties']['error']['properties']['code']['enum']), set(s.RECOVERY))
        self.assertEqual(set(schema['goal']['properties']['status']['enum']), s.STATUSES)
        self.assertEqual(set(schema['mail_metadata']['properties']['kind']['enum']), s.KINDS)
        self.add()
        ident = self.post()
        records = {'goals': s.read_goals(self.root), 'goal': s.exact_goal(self.root, 'task')['goal'],
                   'mail_metadata': s.exact_mail(self.root, ident)['metadata']}
        for name, record in records.items():
            self.assertLessEqual(set(schema[name]['required']), record.keys())
            self.assertLessEqual(record.keys(), schema[name]['properties'].keys())
        for pointer in contract['schemas'].values():
            path, name = pointer.split('#/$defs/')
            self.assertIn(name, json.loads((KIT/path).read_text())['$defs'])


if __name__ == '__main__':
    unittest.main()
