#!/usr/bin/env python3
"""Read exact-chat policy and, when explicitly enabled, open one visible launcher.

No coordination policy is written. Launch receipts are separate installation-wide
metadata. Pending/unknown attempts are never retried merely because time passed;
a healthy response clears that ambiguity. No model, browser or credentials API.
"""

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PureWindowsPath
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from collaboration_policy import PolicyError, allow_provider, default_policy_path, load_snapshot


COOLDOWN_SECONDS = 30.0
MAX_RESPONSE = 65536


class StartError(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def service_url(base_url):
    """Accept a literal loopback address only, with no credentials or extra URL."""
    try:
        parsed = urlsplit(base_url)
        host = parsed.hostname
        if parsed.scheme != "http" or not host:
            raise ValueError()
        if not ipaddress.ip_address(host).is_loopback:
            raise ValueError()
        if (parsed.username is not None or parsed.password is not None
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or parsed.port is None):
            raise ValueError()
    except (ValueError, TypeError):
        raise StartError("invalid_loopback_url") from None
    return base_url.rstrip("/") + "/api/service"


def health(base_url, installation_root, timeout=1.0):
    """Only connection-refused is definitely offline; unknown services do not launch."""
    endpoint = service_url(base_url)
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        with opener.open(Request(endpoint, method="GET"), timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE + 1)
            if response.status != 200 or len(raw) > MAX_RESPONSE:
                return {"status": "unknown", "reason": "invalid_health_response"}
        value = json.loads(raw.decode("utf-8"))
    except HTTPError:
        return {"status": "unknown", "reason": "health_http_error"}
    except URLError as exc:
        reason = exc.reason
        if isinstance(reason, ConnectionRefusedError) or getattr(reason, "errno", None) in (61, 111, 10061):
            return {"status": "offline", "reason": "connection_refused"}
        return {"status": "unknown", "reason": "health_unavailable"}
    except (OSError, ValueError, UnicodeError):
        return {"status": "unknown", "reason": "health_unavailable"}
    service = value.get("service", value) if isinstance(value, dict) else None
    if not isinstance(service, dict):
        return {"status": "unknown", "reason": "invalid_health_response"}
    features = service.get("features")
    if not isinstance(features, dict) or features.get("codex_binding") is not True:
        return {"status": "unknown", "reason": "unsupported_service"}
    for key in ("app", "name"):
        if key in service and service[key] != "antigravity-console":
            return {"status": "unknown", "reason": "service_identity_mismatch"}
    has_installation_identity = False
    for key in ("installation_root", "root"):
        if key in service:
            has_installation_identity = True
            observed = service[key]
            if not isinstance(observed, str) or Path(observed).resolve() != Path(installation_root).resolve():
                return {"status": "unknown", "reason": "installation_identity_mismatch"}
    if not has_installation_identity:
        return {"status": "unknown", "reason": "legacy_service_without_installation_identity"}
    if service.get("stopping") is True or service.get("reloading") is True:
        return {"status": "unknown", "reason": "service_transition"}
    return {"status": "ready", "reason": "verified_service"}


def launcher_argv(launcher_path, platform=None):
    """Build argv, never a POSIX shell string. Windows cmd paths reject metacharacters."""
    platform = platform or sys.platform
    if not isinstance(launcher_path, str) or not launcher_path or any(ord(c) < 32 for c in launcher_path):
        raise StartError("invalid_launcher_path")
    if platform == "win32":
        if not PureWindowsPath(launcher_path).is_absolute() or launcher_path.startswith("\\\\"):
            raise StartError("invalid_launcher_path")
        if any(c in launcher_path for c in '&|<>^%!"()'):
            raise StartError("unsafe_windows_launcher_path")
        if PureWindowsPath(launcher_path).suffix.lower() != ".cmd":
            raise StartError("unsupported_launcher")
        return ["cmd.exe", "/d", "/v:off", "/s", "/c", 'call "' + launcher_path + '"']
    if platform != "darwin":
        raise StartError("automatic_start_unsupported_platform")
    if not Path(launcher_path).is_absolute():
        raise StartError("invalid_launcher_path")
    if Path(launcher_path).suffix != ".command":
        raise StartError("unsupported_launcher")
    return ["/usr/bin/open", "-a", "Terminal", launcher_path]


def resolve_launcher(launcher_path, platform=None):
    platform = platform or sys.platform
    if not isinstance(launcher_path, str) or not launcher_path:
        raise StartError("launcher_not_configured")
    path = Path(launcher_path)
    if not path.is_absolute():
        raise StartError("invalid_launcher_path")
    if path.is_dir():
        names = (("Antigravity.command", "Start-Agy.command") if platform == "darwin"
                 else ("Antigravity.cmd", "Start-Agy.cmd") if platform == "win32"
                 else ("Start-Agy.sh",))
        candidates = [path / name for name in names if (path / name).is_file()]
        if len(candidates) != 1:
            raise StartError("launcher_directory_ambiguous_or_missing")
        path = candidates[0]
    if not path.is_file():
        raise StartError("launcher_missing")
    # Keep the configured path spelling; do not follow a different executable name.
    argv = launcher_argv(str(path), platform)
    return path, argv


def receipt_paths(policy_path, installation_root):
    key = hashlib.sha256(str(Path(installation_root).resolve()).encode("utf-8")).hexdigest()[:24]
    folder = Path(policy_path).parent / "console-start-attempts"
    return folder, folder / (key + ".json"), folder / (key + ".lock")


def read_receipt(path):
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(value, dict) or value.get("status") not in ("pending", "unknown", "ready")
                or type(value.get("last_launch_at")) not in (float, int)):
            raise ValueError()
        return value
    except (OSError, ValueError, UnicodeError):
        raise StartError("launch_receipt_unreadable") from None


def save_receipt(path, value):
    descriptor, temp_path = tempfile.mkstemp(prefix=".attempt-", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def visible_launch(argv, platform=None):
    platform = platform or sys.platform
    options = {"shell": False, "stdin": subprocess.DEVNULL,
               "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if platform == "win32":
        options["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x10)
    subprocess.Popen(argv, **options)


def run(thread_id, installation_root, policy_path=None, ensure_running=False,
        base_url="http://127.0.0.1:8765", wait_seconds=10.0, platform=None,
        probe=None, launch=None, now=None, sleep=None):
    """Dependencies may be supplied for isolated tests; defaults are real host operations."""
    policy_path = Path(policy_path or default_policy_path())
    platform = platform or sys.platform
    probe = probe or health
    launch = launch or visible_launch
    now = now or time.time
    sleep = sleep or time.sleep
    result = {"provider": "agy", "launched": False, "ready": False}
    try:
        if not thread_id:
            raise StartError("missing_thread_id")
        snapshot = load_snapshot(policy_path, thread_id, installation_root)
        allowed = allow_provider(snapshot["policy"], thread_id, "agy")
        if allowed.get("allowed") is not True:
            return dict(result, status="blocked", reason=allowed.get("reason", "provider_paused"))
        service_url(base_url)
        observed = probe(base_url, installation_root)
        folder, receipt, lock = receipt_paths(policy_path, installation_root)
        if observed.get("status") == "ready":
            # A read-only probe never creates or edits launch-attempt metadata.
            if ensure_running and receipt.exists():
                try:
                    lock.mkdir()
                except FileExistsError:
                    return dict(result, status="ready", ready=True, reason="verified_service")
                try:
                    previous = read_receipt(receipt)
                    if previous:
                        previous["status"] = "ready"
                        save_receipt(receipt, previous)
                finally:
                    lock.rmdir()
            return dict(result, status="ready", ready=True, reason="verified_service")
        if not ensure_running:
            return dict(result, status=observed.get("status", "unknown"), reason=observed.get("reason", "not_ready"))
        if snapshot.get("auto_start_console") is not True:
            return dict(result, status="not_started", reason="automatic_start_disabled")
        if observed.get("status") != "offline":
            return dict(result, status="unknown", reason=observed.get("reason", "health_unknown"))
        _launcher, argv = resolve_launcher(snapshot.get("launcher_path"), platform)
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            lock.mkdir(mode=0o700)
        except FileExistsError:
            return dict(result, status="pending", reason="another_start_attempt")
        try:
            # A pause saved during the first health probe must still prevent launch.
            snapshot = load_snapshot(policy_path, thread_id, installation_root)
            allowed = allow_provider(snapshot["policy"], thread_id, "agy")
            if allowed.get("allowed") is not True:
                return dict(result, status="blocked", reason=allowed.get("reason", "provider_paused"))
            if snapshot.get("auto_start_console") is not True:
                return dict(result, status="not_started", reason="automatic_start_disabled")
            _launcher, argv = resolve_launcher(snapshot.get("launcher_path"), platform)
            previous = read_receipt(receipt)
            if previous.get("status") in ("pending", "unknown"):
                return dict(result, status=previous["status"], reason="previous_start_unresolved")
            attempted_at = now()
            if previous and attempted_at - previous["last_launch_at"] < COOLDOWN_SECONDS:
                return dict(result, status="not_started", reason="startup_cooldown")
            save_receipt(receipt, {"status": "pending", "last_launch_at": attempted_at})
            try:
                launch(argv, platform)
                result["launched"] = True
            except (OSError, subprocess.SubprocessError):
                save_receipt(receipt, {"status": "unknown", "last_launch_at": attempted_at})
                return dict(result, status="unknown", reason="launcher_outcome_unknown")
        finally:
            lock.rmdir()
        # Wall-clock adjustments cannot extend this bounded wait indefinitely.
        deadline = time.monotonic() + min(max(wait_seconds, 0.0), 60.0)
        observed = {"status": "unknown", "reason": "startup_timeout"}
        while time.monotonic() < deadline:
            observed = probe(base_url, installation_root)
            if observed.get("status") == "ready":
                break
            sleep(min(0.25, max(0.0, deadline - time.monotonic())))
        try:
            lock.mkdir(mode=0o700)
        except FileExistsError:
            return dict(result, status="pending", reason="another_start_attempt")
        try:
            ready = observed.get("status") == "ready"
            save_receipt(receipt, {"status": "ready" if ready else "unknown", "last_launch_at": attempted_at})
        finally:
            lock.rmdir()
        return dict(result, status="ready" if ready else "unknown", ready=ready,
                    reason="verified_service" if ready else "startup_timeout")
    except (PolicyError, StartError):
        # PolicyError text can contain input paths; only return the stable error class.
        return dict(result, status="blocked", reason="policy_or_launcher_invalid")
    except (OSError, KeyError, TypeError, ValueError):
        return dict(result, status="unknown", reason="startup_state_unavailable")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thread-id", default=os.environ.get("CODEX_THREAD_ID"))
    parser.add_argument("--installation-root", required=True)
    parser.add_argument("--policy-file")
    parser.add_argument("--ensure-running", action="store_true", help="Allow one explicitly enabled visible launcher attempt")
    parser.add_argument("--console-url", default="http://127.0.0.1:8765")
    parser.add_argument("--wait-seconds", type=float, default=10.0)
    args = parser.parse_args(argv)
    result = run(args.thread_id, args.installation_root, args.policy_file,
                 args.ensure_running, args.console_url, args.wait_seconds)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
