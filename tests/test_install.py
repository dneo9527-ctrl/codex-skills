"""Observable installer preservation and recovery checks in disposable homes."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('skill_install', ROOT / 'skills/codex-project-memory/install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='Skill home with spaces ')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.home = self.root / 'Codex Home'

    def test_complete_install_preserves_configuration_and_refuses_second_copy(self):
        self.home.mkdir()
        (self.home / 'AGENTS.md').write_bytes(b'Existing instructions\n')
        (self.home / 'config.toml').write_bytes(b'approval_policy="on-request"\n')
        before = {p.name:p.read_bytes() for p in self.home.iterdir()}
        result = installer.install(self.home)
        target = Path(result['installed'])
        self.assertEqual({p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()}, set(installer.FILES))
        for name in installer.FILES:
            self.assertEqual((target/name).read_bytes(), (installer.SOURCE/name).read_bytes())
            self.assertEqual((target/name).stat().st_mode & 0o777, 0o600)
        self.assertEqual(target.stat().st_mode & 0o777, 0o700)
        self.assertEqual({n:(self.home/n).read_bytes() for n in before}, before)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            installer.install(self.home)
        self.assertEqual((target/'SKILL.md').read_bytes(), (installer.SOURCE/'SKILL.md').read_bytes())

    def test_unknown_file_and_linked_destination_are_preserved(self):
        skills = self.home/'skills'; skills.mkdir(parents=True)
        target = skills/'codex-project-memory'; target.write_text('unrelated')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            installer.install(self.home)
        self.assertEqual(target.read_text(), 'unrelated')
        target.unlink()
        protected = self.root/'protected'; protected.mkdir(); (protected/'marker').write_text('keep')
        target.symlink_to(protected, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            installer.install(self.home)
        self.assertEqual((protected/'marker').read_text(), 'keep')

    def test_partial_copy_failure_cleans_only_claimed_skill(self):
        self.home.mkdir(); (self.home/'AGENTS.md').write_text('keep')
        with patch.object(installer.shutil, 'copyfile', side_effect=OSError('synthetic failure')):
            with self.assertRaises(OSError):
                installer.install(self.home)
        self.assertFalse((self.home/'skills/codex-project-memory').exists())
        self.assertEqual((self.home/'AGENTS.md').read_text(), 'keep')

    def test_incomplete_or_linked_source_is_rejected_before_creating_home(self):
        source = self.root/'source'; source.mkdir()
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            installer.install(self.home, source)
        self.assertFalse(self.home.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
