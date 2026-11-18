#!/usr/bin/env python3
"""Read exact-chat collaboration preferences; never change them or call a model."""
import argparse
import json
import os
from pathlib import Path
import re
import sys

PROVIDERS = ('agy', 'muse', 'claude')
THREAD_ID = re.compile(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}')
MAX_POLICY_BYTES = 8 * 1024 * 1024


class PolicyError(ValueError):
    pass


def valid_thread(thread_id):
    if not isinstance(thread_id, str) or not THREAD_ID.fullmatch(thread_id):
        raise PolicyError('invalid_thread_id')
    return thread_id


def strict_bool(value, name):
    if type(value) is not bool:
        raise PolicyError('invalid_' + name)
    return value


def validate_policy(policy, thread_id):
    valid_thread(thread_id)
    if not isinstance(policy, dict) or type(policy.get('schema_version')) is not int or policy['schema_version'] != 1:
        raise PolicyError('unsupported_policy_schema')
    if policy.get('codex_thread_id') != thread_id:
        raise PolicyError('policy_thread_mismatch')
    enabled = strict_bool(policy.get('enabled'), 'master_enabled')
    providers = policy.get('providers')
    if not isinstance(providers, dict) or set(providers) != set(PROVIDERS):
        raise PolicyError('invalid_providers')
    return {'schema_version': 1, 'codex_thread_id': thread_id, 'enabled': enabled,
            'providers': {key: {'enabled': strict_bool(
                providers[key].get('enabled') if isinstance(providers[key], dict) else None,
                key + '_enabled')} for key in PROVIDERS}}


def allow_provider(policy, thread_id, provider):
    policy = validate_policy(policy, thread_id)
    if provider not in PROVIDERS:
        return {'allowed': False, 'provider': provider, 'reason': 'unsupported_provider'}
    reason = ('master_paused' if not policy['enabled'] else
              'provider_disabled' if not policy['providers'][provider]['enabled'] else 'enabled')
    return {'allowed': reason == 'enabled', 'provider': provider, 'reason': reason}


def from_bridge(payload, thread_id):
    """Canonical state owns the master; the legacy alias means effective Agy."""
    valid_thread(thread_id)
    if not isinstance(payload, dict) or payload.get('codex_thread_id') != thread_id:
        raise PolicyError('bridge_thread_mismatch')
    if 'multi_ai_collaboration' in payload or payload.get('multi_ai_collaboration_supported') is True:
        if payload.get('multi_ai_collaboration_supported') is not True:
            raise PolicyError('missing_policy_support')
        return validate_policy(payload.get('multi_ai_collaboration'), thread_id)
    if 'multi_ai_collaboration_supported' in payload and payload['multi_ai_collaboration_supported'] is not False:
        raise PolicyError('invalid_policy_support')
    # An old server knows only Agy: do not make new providers available by upgrade.
    enabled = strict_bool(payload.get('collaboration_enabled'), 'legacy_enabled')
    return {'schema_version': 1, 'codex_thread_id': thread_id, 'enabled': enabled,
            'providers': {key: {'enabled': key == 'agy'} for key in PROVIDERS}}


def default_policy_path():
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/AgyConsole/coordination.json'
    if os.name == 'nt':
        local = os.environ.get('LOCALAPPDATA')
        if not local:
            raise PolicyError('missing_localappdata')
        return Path(local) / 'AgyConsole/coordination.json'
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'agy-console/coordination.json'


def same_installation(actual, expected):
    if not isinstance(actual, str) or not actual or not isinstance(expected, (str, Path)):
        return False
    actual_path, expected_path = Path(actual).expanduser(), Path(expected).expanduser()
    return (actual_path.is_absolute() and expected_path.is_absolute()
            and actual_path.resolve() == expected_path.resolve())


def read_json(path):
    try:
        with Path(path).open('rb') as stream:
            raw = stream.read(MAX_POLICY_BYTES + 1)
        if len(raw) > MAX_POLICY_BYTES:
            raise PolicyError('policy_too_large')
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise PolicyError('duplicate_policy_key')
                result[key] = value
            return result
        return json.loads(raw.decode('utf-8'), object_pairs_hook=unique_pairs)
    except PolicyError:
        raise
    except (OSError, ValueError, UnicodeError):
        raise PolicyError('policy_unavailable') from None


def load_snapshot(policy_path, thread_id, installation_root):
    valid_thread(thread_id)
    data = read_json(policy_path)
    if not isinstance(data, dict) or type(data.get('schema_version')) is not int or data['schema_version'] != 1:
        raise PolicyError('unsupported_snapshot_schema')
    if data.get('ready') is not True:
        raise PolicyError('snapshot_not_ready')
    if not same_installation(data.get('installation_root'), installation_root):
        raise PolicyError('installation_mismatch')
    threads = data.get('threads')
    item = threads.get(thread_id) if isinstance(threads, dict) else None
    if not isinstance(item, dict):
        raise PolicyError('thread_not_configured')
    policy = validate_policy(item.get('multi_ai_collaboration'), thread_id)
    auto_start = strict_bool(item.get('auto_start_console'), 'auto_start_console')
    launcher = data.get('launcher')
    if not isinstance(launcher, dict) or not isinstance(launcher.get('path'), str):
        raise PolicyError('invalid_launcher_metadata')
    # Return only this chat and launch metadata, never all-chat settings.
    return {'policy': policy, 'auto_start_console': auto_start,
            'launcher_path': launcher['path'], 'installation_root': data['installation_root']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--thread-id', default=os.environ.get('CODEX_THREAD_ID'))
    parser.add_argument('--provider', required=True, choices=PROVIDERS)
    parser.add_argument('--bridge-json', action='store_true', help='Read bridge --ensure JSON from stdin')
    parser.add_argument('--policy-file', type=Path)
    parser.add_argument('--installation-root', help='Known configured console installation, required for snapshot mode')
    args = parser.parse_args()
    try:
        if args.bridge_json:
            if args.policy_file or args.installation_root:
                raise PolicyError('conflicting_policy_sources')
            raw = sys.stdin.buffer.read(MAX_POLICY_BYTES + 1)
            if len(raw) > MAX_POLICY_BYTES:
                raise PolicyError('policy_too_large')
            policy = from_bridge(json.loads(raw), args.thread_id)
            result = {'policy': policy, 'source': 'bridge'}
        else:
            if not args.installation_root:
                raise PolicyError('installation_root_required')
            result = load_snapshot(args.policy_file or default_policy_path(), args.thread_id, args.installation_root)
            result['source'] = 'snapshot'
        result.update(allow_provider(result['policy'], args.thread_id, args.provider))
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result['allowed'] else 3
    except (PolicyError, ValueError, OSError) as error:
        # Fixed error codes only: malformed private input is never echoed.
        reason = str(error) if isinstance(error, PolicyError) else 'invalid_policy_input'
        print(json.dumps({'allowed': False, 'reason': reason}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
