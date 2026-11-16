import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/codex-project-memory/scripts/project_memory.py'
spec = importlib.util.spec_from_file_location('project_memory', SCRIPT)
memory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(memory)


class ProjectMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.env = dict(os.environ, CODEX_HOME=str(self.base), CODEX_THREAD_ID='thread-a')
        self.profile = {'project': 'Example', 'role': 'Maintainer', 'focus': ['Python'],
                        'constraints': ['Do not deploy'], 'success_checks': ['Run relevant checks'],
                        'methods': [], 'resources': []}
        self.req = {'expected_revision': None, 'enabled': True, 'profile': self.profile}

    def run_cli(self, *args, data=None, env=None):
        proc = subprocess.run([sys.executable, str(SCRIPT), *args], env=env or self.env,
                              input=json.dumps(data) if data else None, text=True, capture_output=True)
        value = json.loads(proc.stdout if proc.returncode == 0 else proc.stderr)
        return proc.returncode, value

    def create(self):
        code, result = self.run_cli('save', data=self.req)
        self.assertEqual(code, 0, result)
        return result

    def cp(self, **extra):
        path = self.base / 'task-checkpoints/thread-a.json'
        path.parent.mkdir(exist_ok=True)
        data = dict(thread_id='thread-a', status='waiting', waiting_for_user=True,
                    needs_approval=True, constraints=['Do not publish'], goal='Build',
                    remaining=['Need approval'], next_action='Wait', blockers=['Approval'],
                    external_actions={'sent_receipt': 'exact-123', 'unknown': True}, **extra)
        path.write_text(json.dumps(data))
        return path, data

    def test_missing_is_read_only(self):
        code, data = self.run_cli('show')
        self.assertEqual(code, 0)
        self.assertFalse(data['found'])
        self.assertFalse((self.base / 'project-memory').exists())

    def test_create_and_read(self):
        saved = self.create()
        code, shown = self.run_cli('show')
        self.assertEqual(code, 0)
        self.assertEqual(shown['profile'], self.profile)
        self.assertEqual(shown['revision'], saved['revision'])
        self.assertEqual(Path(saved['path']).stat().st_mode & 0o777, 0o600)
        self.assertEqual(Path(saved['path']).parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.base / 'project-memory/learning').stat().st_mode & 0o777, 0o700)

    def test_threads_are_isolated_even_in_same_working_directory(self):
        self.create()
        code, shown = self.run_cli('show', env=dict(self.env, CODEX_THREAD_ID='thread-b'))
        self.assertEqual(code, 0)
        self.assertFalse(shown['found'])

    def test_missing_or_traversal_identity_rejected(self):
        for thread in ('', '../thread-a', '*'):
            code, result = self.run_cli('save', data=self.req, env=dict(self.env, CODEX_THREAD_ID=thread))
            self.assertEqual(code, 2, result)

    def test_wrong_revision_preserves_state(self):
        saved = self.create()
        before = Path(saved['path']).read_bytes()
        request = copy.deepcopy(self.req)
        request['profile']['role'] = 'Updated'
        code, result = self.run_cli('save', data=request)
        self.assertEqual(code, 2)
        self.assertIn('conflict', result['error'])
        self.assertEqual(before, Path(saved['path']).read_bytes())

    def test_noop_does_not_rewrite_or_record_learning(self):
        saved = self.create()
        before = Path(saved['path']).stat().st_mtime_ns
        self.req['expected_revision'] = saved['revision']
        code, result = self.run_cli('save', data=self.req)
        self.assertEqual(code, 0)
        self.assertFalse(result['saved'])
        self.assertEqual(before, Path(saved['path']).stat().st_mtime_ns)
        self.assertEqual(len(list((self.base / 'project-memory/learning').glob('*/*.json'))), 1)

    def test_real_concurrent_writers_have_one_winner(self):
        saved = self.create()
        requests = []
        for name in ('First', 'Second'):
            req = copy.deepcopy(self.req)
            req['expected_revision'] = saved['revision']
            req['profile']['role'] = name
            requests.append(req)
        processes = [subprocess.Popen([sys.executable, str(SCRIPT), 'save'], env=self.env,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                     for _ in requests]
        for process, request in zip(processes, requests):
            process.stdin.write(json.dumps(request))
            process.stdin.close()
            process.stdin = None
        for process in processes:
            process.communicate(timeout=10)
        self.assertEqual(sorted(p.returncode for p in processes), [0, 2])

    def test_oversize_preserves_old_profile(self):
        saved = self.create()
        before = Path(saved['path']).read_bytes()
        req = copy.deepcopy(self.req)
        req['expected_revision'] = saved['revision']
        req['profile']['constraints'] = [str(i) + 'x' * 590 for i in range(6)]
        req['profile']['success_checks'] = ['y' * 590] * 6
        code, result = self.run_cli('save', data=req)
        self.assertEqual(code, 2, result)
        self.assertEqual(before, Path(saved['path']).read_bytes())

    def test_methods_require_evidence_and_expiry_conditions(self):
        self.req['profile']['methods'] = [{'when': 'Always', 'do': 'Guess'}]
        code, result = self.run_cli('save', data=self.req)
        self.assertEqual(code, 2)

    def test_no_arbitrary_id_or_unknown_fields(self):
        self.assertNotEqual(subprocess.run([sys.executable, str(SCRIPT), 'save', '--id', 'other'],
                                         env=self.env, capture_output=True).returncode, 0)
        self.req['auto_resumable'] = True
        code, result = self.run_cli('save', data=self.req)
        self.assertEqual(code, 2)

    def test_checkpoint_flags_and_canonical_state_untouched(self):
        path, cp = self.cp()
        before = path.read_bytes()
        self.create()
        code, shown = self.run_cli('show')
        self.assertEqual(code, 0)
        self.assertTrue(shown['checkpoint']['waiting_for_user'])
        self.assertTrue(shown['checkpoint']['needs_approval'])
        self.assertTrue(shown['checkpoint']['details_required'])
        self.assertEqual(before, path.read_bytes())

    def test_large_checkpoint_never_silently_truncates_constraints(self):
        self.cp(extra_context='x')
        path = self.base / 'task-checkpoints/thread-a.json'
        cp = json.loads(path.read_text())
        cp['constraints'] = ['critical:' + 'x' * 3000]
        path.write_text(json.dumps(cp))
        code, shown = self.run_cli('show')
        self.assertEqual(code, 0)
        self.assertNotIn('brief', shown['checkpoint'])
        self.assertTrue(shown['checkpoint']['details_required'])

    def test_handoff_preserves_additional_action_fields_and_not_compacted(self):
        path, cp = self.cp()
        out = self.base / 'handoff.json'
        code, result = self.run_cli('handoff', '--out', str(out))
        self.assertEqual(code, 0, result)
        exported = json.loads(out.read_text())
        self.assertEqual(exported['checkpoint'], cp)
        self.assertFalse(exported['context_compacted'])
        self.assertEqual(out.stat().st_mode & 0o777, 0o600)
        code, result = self.run_cli('handoff', '--out', str(out))
        self.assertEqual(code, 2)

    def test_oversized_handoff_refuses_instead_of_losing_data(self):
        self.cp(verification=['x' * 17000])
        out = self.base / 'handoff.json'
        code, result = self.run_cli('handoff', '--out', str(out))
        self.assertEqual(code, 2)
        self.assertFalse(out.exists())

    def test_disabled_profile_hides_guidance_and_report_events(self):
        saved = self.create()
        self.req.update(expected_revision=saved['revision'], enabled=False)
        code, result = self.run_cli('save', data=self.req)
        self.assertEqual(code, 0)
        code, shown = self.run_cli('show')
        self.assertNotIn('profile', shown)
        self.assertFalse(shown['enabled'])
        code, report = self.run_cli('report')
        self.assertEqual(report['event_count'], 0)

    def test_learning_records_real_deltas_only(self):
        saved = self.create()
        self.req['expected_revision'] = saved['revision']
        method = {'when': 'Test failure', 'do': 'Read exact assertion',
                  'evidence': 'Fixture verification passed', 'recheck': 'Test harness changes'}
        self.req['profile']['methods'] = [method]
        self.run_cli('save', data=self.req)
        code, report = self.run_cli('report')
        self.assertEqual(code, 0)
        self.assertEqual(report['event_count'], 2)
        self.assertEqual(report['events'][0]['kind'], 'update')
        self.assertEqual(report['events'][0]['methods_added'], [method])
        self.assertEqual(report['events'][1]['kind'], 'initialization')

    def test_enable_disable_preserves_hidden_profile_with_revision_check(self):
        saved = self.create()
        code, disabled = self.run_cli('disable', data={'expected_revision': saved['revision']})
        self.assertEqual(code, 0, disabled)
        code, shown = self.run_cli('show')
        self.assertFalse(shown['enabled'])
        self.assertNotIn('profile', shown)
        code, conflict = self.run_cli('enable', data={'expected_revision': saved['revision']})
        self.assertEqual(code, 2)
        self.assertIn('conflict', conflict['error'])
        code, enabled = self.run_cli('enable', data={'expected_revision': disabled['revision']})
        self.assertEqual(code, 0, enabled)
        code, shown = self.run_cli('show')
        self.assertTrue(shown['enabled'])
        self.assertEqual(shown['profile'], self.profile)

    def test_report_defaults_to_current_chat_and_all_chats_is_explicit(self):
        self.create()
        code, other = self.run_cli('save', data=self.req, env=dict(self.env, CODEX_THREAD_ID='thread-b'))
        self.assertEqual(code, 0, other)
        code, local = self.run_cli('report')
        self.assertEqual(local['scope'], 'current_chat')
        self.assertEqual({e['thread_id'] for e in local['events']}, {'thread-a'})
        code, all_chats = self.run_cli('report', '--all-chats')
        self.assertEqual(all_chats['scope'], 'all_local_chats')
        self.assertEqual({e['thread_id'] for e in all_chats['events']}, {'thread-a', 'thread-b'})
        code, no_id = self.run_cli('report', env=dict(self.env, CODEX_THREAD_ID=''))
        self.assertEqual(code, 2)

    def test_checkpoint_requires_embedded_identity(self):
        path, cp = self.cp()
        cp.pop('thread_id')
        path.write_text(json.dumps(cp))
        code, result = self.run_cli('show')
        self.assertEqual(code, 2)
        self.assertIn('identity mismatch', result['error'])

    def test_corrupt_profile_or_identity_refuses(self):
        saved = self.create()
        path = Path(saved['path'])
        obj = json.loads(path.read_text())
        obj['thread_id'] = 'other'
        path.write_text(json.dumps(obj))
        code, result = self.run_cli('show')
        self.assertEqual(code, 2)

    def test_report_is_bounded_and_reports_omissions(self):
        saved = self.create()
        for i in range(32):
            self.req['expected_revision'] = saved['revision']
            self.req['profile']['role'] = 'Role ' + str(i)
            code, saved = self.run_cli('save', data=self.req)
            self.assertEqual(code, 0)
        code, report = self.run_cli('report')
        self.assertEqual(report['event_count'], 33)
        self.assertGreater(report['omitted_count'], 0)
        self.assertLessEqual(len(report['events']), 30)

    def test_symlink_and_corrupt_checkpoint_refuse(self):
        folder = self.base / 'project-memory'
        folder.mkdir()
        target = self.base / 'protected.json'
        target.write_text('{}')
        (folder / 'thread-a.json').symlink_to(target)
        code, result = self.run_cli('save', data=self.req)
        self.assertEqual(code, 2)
        self.assertEqual(target.read_text(), '{}')


if __name__ == '__main__':
    unittest.main(verbosity=2)
