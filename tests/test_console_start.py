"""Isolated startup tests. No user policy, launcher, service or model is touched."""

import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "external-ai-team" / "scripts" / "console_start.py"
# Keep these tests independent of the policy implementation's own test suite.
stub = types.ModuleType("collaboration_policy")
stub.PolicyError = type("PolicyError", (ValueError,), {})
stub.load_snapshot = Mock()
stub.allow_provider = Mock()
stub.default_policy_path = Mock()
spec = importlib.util.spec_from_file_location("isolated_console_start", SCRIPT)
console = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"collaboration_policy": stub}):
    spec.loader.exec_module(console)


class ConsoleStartTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.root = self.home / "installation"
        self.root.mkdir()
        self.policy = self.home / "coordination.json"
        self.policy.write_text('{"isolated":"unchanged"}', encoding="utf-8")
        self.original = self.policy.read_bytes()
        self.launcher = self.home / "Antigravity.command"
        self.launcher.write_text("# test fixture: never executed\n", encoding="utf-8")
        self.snapshot = {"policy": {"enabled": True}, "auto_start_console": True,
                         "launcher_path": str(self.launcher)}
        self.loader = patch.object(console, "load_snapshot", return_value=self.snapshot).start()
        self.gate = patch.object(console, "allow_provider", return_value={"allowed": True, "reason": "enabled"}).start()
        self.addCleanup(patch.stopall)
        self.probe = Mock(return_value={"status": "offline", "reason": "connection_refused"})
        self.launch = Mock()

    def tearDown(self):
        self.assertEqual(self.policy.read_bytes(), self.original)

    def run_helper(self, thread_id="test-thread-a", **kw):
        options = dict(policy_path=self.policy, ensure_running=True, platform="darwin",
                       wait_seconds=0, probe=self.probe, launch=self.launch)
        options.update(kw)
        return console.run(thread_id, str(self.root), **options)

    def test_total_pause_does_no_network_launch_or_receipt(self):
        self.gate.return_value = {"allowed": False, "reason": "total_paused"}
        result = self.run_helper()
        self.assertEqual(result["reason"], "total_paused")
        self.probe.assert_not_called()
        self.launch.assert_not_called()
        self.assertFalse((self.home / "console-start-attempts").exists())

    def test_agy_pause_does_no_network_or_launch(self):
        self.gate.return_value = {"allowed": False, "reason": "provider_disabled"}
        self.assertEqual(self.run_helper()["status"], "blocked")
        self.probe.assert_not_called()
        self.launch.assert_not_called()
        self.gate.assert_called_once_with(self.snapshot["policy"], "test-thread-a", "agy")

    def test_invalid_policy_does_no_network_or_launch(self):
        self.loader.side_effect = console.PolicyError("private detail must not be emitted")
        result = self.run_helper()
        self.assertEqual(result["reason"], "policy_or_launcher_invalid")
        self.assertNotIn("private", json.dumps(result))
        self.probe.assert_not_called()
        self.launch.assert_not_called()

    def test_missing_thread_does_no_policy_read(self):
        self.assertEqual(self.run_helper(thread_id="")["status"], "blocked")
        self.loader.assert_not_called()
        self.probe.assert_not_called()

    def test_already_ready_launches_nothing(self):
        self.probe.return_value = {"status": "ready"}
        result = self.run_helper()
        self.assertTrue(result["ready"])
        self.assertFalse(result["launched"])
        self.launch.assert_not_called()
        self.assertFalse((self.home / "console-start-attempts").exists())

    def test_read_only_offline_creates_nothing(self):
        self.assertEqual(self.run_helper(ensure_running=False)["status"], "offline")
        self.launch.assert_not_called()
        self.assertFalse((self.home / "console-start-attempts").exists())

    def test_explicit_autostart_false_never_launches(self):
        self.snapshot["auto_start_console"] = False
        self.assertEqual(self.run_helper()["reason"], "automatic_start_disabled")
        self.probe.assert_called_once()
        self.launch.assert_not_called()

    def test_unknown_health_never_launches(self):
        self.probe.return_value = {"status": "unknown", "reason": "service_identity_mismatch"}
        self.assertEqual(self.run_helper()["reason"], "service_identity_mismatch")
        self.launch.assert_not_called()

    def test_invalid_launcher_values_never_launch(self):
        for path in ("", "relative.command", str(self.home / "missing.command"), str(self.root / "wrong.py")):
            with self.subTest(path=path):
                self.snapshot["launcher_path"] = path
                self.assertEqual(self.run_helper()["status"], "blocked")
        self.launch.assert_not_called()

    def test_wrong_existing_launcher_extension_never_launches(self):
        wrong = self.home / "start.sh"
        wrong.write_text("never execute", encoding="utf-8")
        self.snapshot["launcher_path"] = str(wrong)
        self.assertEqual(self.run_helper()["status"], "blocked")
        self.launch.assert_not_called()

    def test_directory_requires_unique_supported_launcher(self):
        self.assertEqual(console.resolve_launcher(str(self.home), "darwin")[0], self.launcher)
        other = self.home / "Start-Agy.command"
        other.write_text("never execute", encoding="utf-8")
        self.snapshot["launcher_path"] = str(self.home)
        self.assertEqual(self.run_helper()["status"], "blocked")
        self.launch.assert_not_called()

    def test_directory_with_no_launcher_is_rejected(self):
        with self.assertRaises(console.StartError):
            console.resolve_launcher(str(self.root), "darwin")

    def test_linux_does_not_start_shell(self):
        shell = self.home / "Start-Agy.sh"
        shell.write_text("never execute", encoding="utf-8")
        self.snapshot["launcher_path"] = str(shell)
        self.assertEqual(self.run_helper(platform="linux")["status"], "blocked")
        self.launch.assert_not_called()

    def test_mac_argv_uses_visible_terminal_no_shell(self):
        argv = console.launcher_argv(str(self.launcher), "darwin")
        self.assertEqual(argv, ["/usr/bin/open", "-a", "Terminal", str(self.launcher)])
        with patch.object(console.subprocess, "Popen") as popen:
            console.visible_launch(argv, "darwin")
        self.assertIs(popen.call_args.kwargs["shell"], False)
        self.assertEqual(popen.call_args.args[0], argv)

    def test_windows_argv_creates_visible_console_and_rejects_injection(self):
        path = r"C:\Tools with spaces\Start-Agy.cmd"
        argv = console.launcher_argv(path, "win32")
        self.assertEqual(argv, ["cmd.exe", "/d", "/v:off", "/s", "/c", 'call "' + path + '"'])
        with patch.object(console.subprocess, "Popen") as popen:
            console.visible_launch(argv, "win32")
        self.assertEqual(popen.call_args.kwargs["creationflags"], 0x10)
        self.assertIs(popen.call_args.kwargs["shell"], False)
        for bad in ('&', '|', '<', '>', '^', '%', '!', '"', '(', ')', '\n'):
            with self.subTest(character=repr(bad)), self.assertRaises(console.StartError):
                console.launcher_argv("C:\\Tools\\bad" + bad + ".cmd", "win32")
        for bad in (r"\\server\share\start.cmd", r"relative\start.cmd", r"C:\start.exe"):
            with self.assertRaises(console.StartError):
                console.launcher_argv(bad, "win32")

    def test_pause_during_health_prevents_launch(self):
        self.gate.side_effect = [{"allowed": True}, {"allowed": False, "reason": "total_paused"}]
        self.assertEqual(self.run_helper()["reason"], "total_paused")
        self.launch.assert_not_called()

    def test_launch_timeout_unknown_blocks_later_retry_across_chat(self):
        first = self.run_helper()
        self.assertTrue(first["launched"])
        self.assertEqual(first["reason"], "startup_timeout")
        second = self.run_helper(thread_id="test-thread-b", now=lambda: 9999999999.0)
        self.assertEqual(second["reason"], "previous_start_unresolved")
        self.assertEqual(self.launch.call_count, 1)
        _folder, receipt, _lock = console.receipt_paths(self.policy, self.root)
        self.assertEqual(json.loads(receipt.read_text())["status"], "unknown")

    def test_launch_exception_unknown_does_not_retry(self):
        self.launch.side_effect = OSError("not included in result")
        self.assertEqual(self.run_helper()["reason"], "launcher_outcome_unknown")
        self.assertEqual(self.run_helper()["reason"], "previous_start_unresolved")
        self.assertEqual(self.launch.call_count, 1)

    def test_health_success_resolves_unknown_but_keeps_short_cooldown(self):
        self.run_helper(now=lambda: 100.0)
        self.probe.return_value = {"status": "ready"}
        self.assertTrue(self.run_helper(now=lambda: 101.0)["ready"])
        self.probe.return_value = {"status": "offline"}
        self.assertEqual(self.run_helper(now=lambda: 102.0)["reason"], "startup_cooldown")
        self.assertEqual(self.launch.call_count, 1)

    def test_readonly_health_does_not_rewrite_receipt(self):
        self.run_helper()
        _folder, receipt, _lock = console.receipt_paths(self.policy, self.root)
        original = receipt.read_bytes()
        self.probe.return_value = {"status": "ready"}
        self.assertTrue(self.run_helper(ensure_running=False)["ready"])
        self.assertEqual(receipt.read_bytes(), original)

    def test_start_then_ready_is_verified_once(self):
        self.probe.side_effect = [{"status": "offline"}, {"status": "ready"}]
        result = self.run_helper(wait_seconds=0.2)
        self.assertTrue(result["ready"])
        self.assertTrue(result["launched"])
        self.launch.assert_called_once()

    def test_persistent_lock_prevents_another_launch(self):
        folder, _receipt, lock = console.receipt_paths(self.policy, self.root)
        folder.mkdir()
        lock.mkdir()
        self.assertEqual(self.run_helper()["reason"], "another_start_attempt")
        self.launch.assert_not_called()

    def test_concurrent_different_chats_launch_once(self):
        started = threading.Event()
        release = threading.Event()
        outputs = []
        def launching(_argv, _platform):
            started.set()
            release.wait(2)
        self.launch.side_effect = launching
        first = threading.Thread(target=lambda: outputs.append(self.run_helper()))
        first.start()
        self.assertTrue(started.wait(2))
        second = self.run_helper(thread_id="test-thread-b")
        release.set()
        first.join(2)
        self.assertFalse(first.is_alive())
        self.assertEqual(second["reason"], "another_start_attempt")
        self.assertEqual(self.launch.call_count, 1)
        self.assertEqual(len(outputs), 1)

    def test_corrupt_receipt_prevents_blind_launch(self):
        folder, receipt, _lock = console.receipt_paths(self.policy, self.root)
        folder.mkdir()
        receipt.write_text("broken", encoding="utf-8")
        self.assertEqual(self.run_helper()["status"], "blocked")
        self.launch.assert_not_called()

    def test_cli_thread_env_and_readonly_default(self):
        with patch.dict(console.os.environ, {"CODEX_THREAD_ID": "env-thread"}), patch.object(console, "run", return_value={"ready": True}) as run:
            with patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(console.main(["--installation-root", str(self.root)]), 0)
        self.assertEqual(run.call_args.args[0], "env-thread")
        self.assertIs(run.call_args.args[3], False)


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = str(Path(self.temp.name).resolve())
        self.value = {"app": "antigravity-console", "root": self.root,
                      "features": {"codex_binding": True}}
        self.opener = Mock()
        self.patcher = patch.object(console, "build_opener", return_value=self.opener)
        self.build = self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def check(self, value=None):
        response = Mock()
        response.status = 200
        response.read.return_value = json.dumps(self.value if value is None else value).encode()
        self.opener.open.return_value.__enter__ = Mock(return_value=response)
        self.opener.open.return_value.__exit__ = Mock(return_value=False)
        return console.health("http://127.0.0.1:8765", self.root)

    def test_exact_same_installation_is_ready_without_proxy_or_redirect(self):
        self.assertEqual(self.check()["status"], "ready")
        proxy, redirect = self.build.call_args.args
        self.assertEqual(proxy.proxies, {})
        self.assertIsInstance(redirect, console.NoRedirect)
        request = self.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8765/api/service")
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(redirect.redirect_request(None, None, 302, "", {}, "https://example.invalid"))

    def test_wrong_service_or_installation_is_not_ready(self):
        for key, bad in (("app", "other"), ("root", "/another/installation")):
            value = dict(self.value, **{key: bad})
            with self.subTest(key=key):
                self.assertEqual(self.check(value)["status"], "unknown")

    def test_legacy_missing_root_is_not_ready_or_offline(self):
        self.value.pop("root")
        result = self.check()
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason"], "legacy_service_without_installation_identity")

    def test_feature_requires_strict_bool_and_transition_not_ready(self):
        for feature in (False, 1, "true", None):
            self.assertEqual(self.check(dict(self.value, features={"codex_binding": feature}))["status"], "unknown")
        self.assertEqual(self.check(dict(self.value, stopping=True))["status"], "unknown")

    def test_refused_is_offline_timeout_and_redirect_unknown(self):
        for error, status in ((URLError(ConnectionRefusedError(61, "refused")), "offline"),
                              (URLError(TimeoutError()), "unknown"),
                              (HTTPError("http://127.0.0.1:8765", 302, "redirect", {}, None), "unknown")):
            self.opener.open.side_effect = error
            self.assertEqual(console.health("http://127.0.0.1:8765", self.root)["status"], status)

    def test_only_literal_loopback_plain_http_url_is_accepted(self):
        for url in ("https://127.0.0.1:8765", "http://example.com:8765", "http://localhost:8765",
                    "http://user:pass@127.0.0.1:8765", "http://127.0.0.1:8765/path",
                    "http://127.0.0.1:8765/?token=x", "http://127.0.0.1:8765/#fragment"):
            with self.subTest(url=url), self.assertRaises(console.StartError):
                console.service_url(url)
        self.assertEqual(console.service_url("http://[::1]:8765"), "http://[::1]:8765/api/service")
        self.build.assert_not_called()


if __name__ == "__main__":
    unittest.main()
