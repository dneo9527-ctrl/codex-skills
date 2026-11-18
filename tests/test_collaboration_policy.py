import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'skills/external-ai-team/scripts/collaboration_policy.py'
spec = importlib.util.spec_from_file_location('policy', SCRIPT)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)
THREAD = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'


def canonical(enabled=True, agy=True, muse=False, claude=False):
    return {'schema_version': 1, 'codex_thread_id': THREAD, 'enabled': enabled,
            'providers': {k: {'enabled': v} for k, v in zip(policy.PROVIDERS, (agy, muse, claude))}}


class PolicyBehavior(unittest.TestCase):
    def test_master_pause_vetoes_all_enabled_providers(self):
        for key in policy.PROVIDERS:
            self.assertEqual(policy.allow_provider(canonical(False, True, True, True), THREAD, key)['reason'], 'master_paused')

    def test_independent_providers_are_not_a_broadcast(self):
        p = canonical(True, False, True, True)
        self.assertFalse(policy.allow_provider(p, THREAD, 'agy')['allowed'])
        self.assertTrue(policy.allow_provider(p, THREAD, 'muse')['allowed'])
        self.assertTrue(policy.allow_provider(p, THREAD, 'claude')['allowed'])
        self.assertEqual(p, canonical(True, False, True, True))

    def test_canonical_owns_master_even_when_legacy_agy_false(self):
        p = policy.from_bridge({'codex_thread_id': THREAD, 'multi_ai_collaboration_supported': True,
                               'multi_ai_collaboration': canonical(True, False, True), 'collaboration_enabled': False}, THREAD)
        self.assertTrue(policy.allow_provider(p, THREAD, 'muse')['allowed'])
        self.assertFalse(policy.allow_provider(p, THREAD, 'agy')['allowed'])

    def test_legacy_false_never_migrates_to_another_provider(self):
        p = policy.from_bridge({'codex_thread_id': THREAD, 'collaboration_enabled': False}, THREAD)
        self.assertFalse(any(policy.allow_provider(p, THREAD, k)['allowed'] for k in policy.PROVIDERS))

    def test_legacy_true_only_allows_agy(self):
        p = policy.from_bridge({'codex_thread_id': THREAD, 'collaboration_enabled': True}, THREAD)
        self.assertTrue(policy.allow_provider(p, THREAD, 'agy')['allowed'])
        self.assertFalse(policy.allow_provider(p, THREAD, 'claude')['allowed'])

    def test_unknown_provider_does_not_alias_agy(self):
        self.assertEqual(policy.allow_provider(canonical(), THREAD, 'other')['reason'], 'unsupported_provider')

    def test_thread_mismatch_is_rejected(self):
        with self.assertRaises(policy.PolicyError):
            policy.allow_provider(canonical(), OTHER, 'agy')

    def test_damaged_supported_policy_never_falls_back_to_legacy(self):
        for data in (None, {}, canonical()):
            if data and data.get('providers'):
                data['providers']['agy']['enabled'] = 'false'
            with self.assertRaises(policy.PolicyError):
                policy.from_bridge({'codex_thread_id': THREAD, 'multi_ai_collaboration_supported': True,
                                    'multi_ai_collaboration': data, 'collaboration_enabled': True}, THREAD)

    def test_bool_coercion_and_incomplete_providers_are_rejected(self):
        for field in ('schema_version', 'enabled', 'providers'):
            p = canonical(); p[field] = {'schema_version': True, 'enabled': 1, 'providers': {'agy': {'enabled': True}}}[field]
            with self.assertRaises(policy.PolicyError):
                policy.validate_policy(p, THREAD)

    def test_snapshot_is_exact_chat_read_only_and_start_is_separate(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'coordination.json'
            data = {'schema_version': 1, 'ready': True, 'installation_root': d, 'launcher': {'path': ''},
                    'threads': {THREAD: {'multi_ai_collaboration': canonical(), 'auto_start_console': False},
                                OTHER: {'multi_ai_collaboration': {'private_unrelated': 'not-returned'}}}}
            path.write_text(json.dumps(data)); before = path.read_bytes()
            result = policy.load_snapshot(path, THREAD, d)
            self.assertFalse(result['auto_start_console'])
            self.assertNotIn('threads', result)
            self.assertEqual(path.read_bytes(), before)
            with self.assertRaises(policy.PolicyError):
                policy.load_snapshot(path, THREAD, str(Path(d) / 'other'))
            data['ready'] = False; path.write_text(json.dumps(data))
            with self.assertRaises(policy.PolicyError):
                policy.load_snapshot(path, THREAD, d)

    def test_missing_malformed_and_duplicate_snapshot_cannot_enable(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'coordination.json'
            for text in (None, '{', '{"ready":false,"ready":true}'):
                if text is not None:
                    p.write_text(text)
                with self.assertRaises(policy.PolicyError):
                    policy.load_snapshot(p, THREAD, d)

    def test_cli_invalid_input_does_not_echo_private_payload(self):
        out = subprocess.run([sys.executable, str(SCRIPT), '--thread-id', THREAD, '--provider', 'agy', '--bridge-json'],
                             input='{"secret-example":"never-echo-this"', text=True, capture_output=True)
        self.assertEqual(out.returncode, 2)
        self.assertEqual(json.loads(out.stdout), {'allowed': False, 'reason': 'invalid_policy_input'})
        self.assertNotIn('never-echo-this', out.stdout + out.stderr)


if __name__ == '__main__':
    unittest.main()
