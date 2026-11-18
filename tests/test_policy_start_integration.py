"""Exercise the real policy parser with startup; no host services are contacted."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/external-ai-team/scripts'
THREAD = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


policy = load_module('integration_real_policy', SCRIPTS / 'collaboration_policy.py')
with patch.dict(sys.modules, {'collaboration_policy': policy}):
    startup = load_module('integration_real_startup', SCRIPTS / 'console_start.py')


def canonical(thread=THREAD, enabled=True, agy=True, muse=False, claude=False):
    return {'schema_version': 1, 'codex_thread_id': thread, 'enabled': enabled,
            'providers': {key: {'enabled': value} for key, value in
                          zip(('agy', 'muse', 'claude'), (agy, muse, claude))}}


class RealPolicyStartupIntegration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.installation = self.folder / 'installation'
        self.installation.mkdir()
        self.launcher = self.folder / 'Antigravity.command'
        self.launcher.write_text('# fixture, never executed\n')
        self.path = self.folder / 'coordination.json'
        self.data = {'schema_version': 1, 'ready': True,
                     'installation_root': str(self.installation),
                     'launcher': {'path': str(self.launcher)},
                     'threads': {THREAD: {'multi_ai_collaboration': canonical(),
                                         'auto_start_console': True},
                                 OTHER: {'multi_ai_collaboration': canonical(OTHER, False),
                                         'auto_start_console': False}}}
        self.save()
        self.probe = Mock(return_value={'status': 'offline', 'reason': 'connection_refused'})
        self.launch = Mock()

    def save(self):
        self.path.write_text(json.dumps(self.data), encoding='utf-8')

    def run_start(self, thread=THREAD, **options):
        args = dict(policy_path=self.path, ensure_running=True, platform='darwin',
                    wait_seconds=0, probe=self.probe, launch=self.launch)
        args.update(options)
        return startup.run(thread, str(self.installation), **args)

    def test_normal_actual_snapshot_launches_once_then_becomes_ready(self):
        original = self.path.read_bytes()
        self.probe.side_effect = [{'status': 'offline'}, {'status': 'ready'}]
        result = self.run_start(wait_seconds=0.1)
        self.assertEqual(result['status'], 'ready')
        self.assertTrue(result['launched'])
        self.assertEqual(self.launch.call_count, 1)
        self.assertEqual(self.path.read_bytes(), original)

    def test_master_pause_blocks_with_every_provider_enabled(self):
        self.data['threads'][THREAD]['multi_ai_collaboration'] = canonical(enabled=False, muse=True, claude=True)
        self.save()
        result = self.run_start()
        self.assertEqual(result['reason'], 'master_paused')
        self.probe.assert_not_called()
        self.launch.assert_not_called()
        self.assertFalse((self.folder / 'console-start-attempts').exists())

    def test_muse_enabled_agy_disabled_never_starts_ag(self):
        self.data['threads'][THREAD]['multi_ai_collaboration'] = canonical(agy=False, muse=True)
        self.save()
        result = self.run_start()
        self.assertEqual(result['reason'], 'provider_disabled')
        self.assertTrue(policy.allow_provider(
            policy.load_snapshot(self.path, THREAD, self.installation)['policy'], THREAD, 'muse')['allowed'])
        self.probe.assert_not_called()
        self.launch.assert_not_called()

    def test_canonical_agy_alias_false_keeps_muse_eligible(self):
        data = {'codex_thread_id': THREAD, 'collaboration_enabled': False,
                'multi_ai_collaboration_supported': True,
                'multi_ai_collaboration': canonical(agy=False, muse=True)}
        parsed = policy.from_bridge(data, THREAD)
        self.assertTrue(policy.allow_provider(parsed, THREAD, 'muse')['allowed'])
        self.assertFalse(policy.allow_provider(parsed, THREAD, 'agy')['allowed'])

    def test_legacy_pause_vetoes_every_provider(self):
        parsed = policy.from_bridge({'codex_thread_id': THREAD, 'collaboration_enabled': False}, THREAD)
        for provider in ('agy', 'muse', 'claude'):
            self.assertFalse(policy.allow_provider(parsed, THREAD, provider)['allowed'])

    def test_corrupt_and_not_ready_policy_never_probe_or_launch(self):
        for raw in ('{', '{"ready": true, "ready": false}', json.dumps(dict(self.data, ready=False))):
            with self.subTest(raw=raw[:20]):
                self.path.write_text(raw)
                self.assertEqual(self.run_start()['status'], 'blocked')
        self.probe.assert_not_called()
        self.launch.assert_not_called()

    def test_other_thread_pause_and_missing_thread_are_isolated(self):
        result = self.run_start(thread=OTHER)
        self.assertEqual(result['reason'], 'master_paused')
        self.probe.assert_not_called()
        del self.data['threads'][THREAD]
        self.save()
        self.assertEqual(self.run_start()['status'], 'blocked')
        self.probe.assert_not_called()
        self.launch.assert_not_called()

    def test_nested_thread_mismatch_cannot_inherit_other_thread(self):
        self.data['threads'][THREAD]['multi_ai_collaboration']['codex_thread_id'] = OTHER
        self.save()
        self.assertEqual(self.run_start()['status'], 'blocked')
        self.probe.assert_not_called()
        self.launch.assert_not_called()

    def test_pause_saved_during_initial_probe_prevents_launch(self):
        def probe(*args):
            self.data['threads'][THREAD]['multi_ai_collaboration']['enabled'] = False
            self.save()
            return {'status': 'offline'}
        self.probe.side_effect = probe
        self.assertEqual(self.run_start()['reason'], 'master_paused')
        self.launch.assert_not_called()

    def test_two_ensures_cannot_repeat_an_unresolved_launch(self):
        first = self.run_start()
        second = self.run_start()
        self.assertTrue(first['launched'])
        self.assertEqual(first['status'], 'unknown')
        self.assertFalse(second['launched'])
        self.assertEqual(second['reason'], 'previous_start_unresolved')
        self.assertEqual(self.launch.call_count, 1)

    def test_pause_after_launch_never_grants_new_permission(self):
        def launch(*args):
            self.data['threads'][THREAD]['multi_ai_collaboration']['enabled'] = False
            self.save()
        self.launch.side_effect = launch
        self.probe.side_effect = [{'status': 'offline'}, {'status': 'ready'}]
        result = self.run_start(wait_seconds=0.1)
        self.assertTrue(result['ready'])  # Health is separate from send permission.
        final = policy.load_snapshot(self.path, THREAD, self.installation)
        self.assertFalse(policy.allow_provider(final['policy'], THREAD, 'agy')['allowed'])
        self.assertEqual(self.run_start()['reason'], 'master_paused')
        self.assertEqual(self.launch.call_count, 1)


if __name__ == '__main__':
    unittest.main()
