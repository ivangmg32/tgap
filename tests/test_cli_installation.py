"""Distribution and bootstrap checks that do not install packages."""
import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tgap_cli import cli


class InstallationTests(unittest.TestCase):
    def test_bundle_contains_complete_app_without_live_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = cli.unpack(Path(temporary))
            self.assertTrue((target / 'sandbox/app.py').is_file())
            self.assertTrue((target / 'static/app.js').is_file())
            self.assertTrue((target / 'static/relationships.js').is_file())
            self.assertTrue((target / 'static/live-figures.js').is_file())
            self.assertTrue((target / 'sandbox/analyses.py').is_file())
            self.assertTrue((target / 'sandbox/security.py').is_file())
            self.assertTrue((target / 'sandbox/reporting.py').is_file())
            self.assertTrue((target / 'static/researcher.js').is_file())
            self.assertTrue((target / 'static/auth.js').is_file())
            self.assertIn('Pillow', (target / 'requirements.txt').read_text())
            self.assertEqual(len(list((target / 'publication').glob('*.png'))),12)
            self.assertEqual(len(list((target / 'data/datasets').glob('*.json'))), 8)
            for filename in ('users.txt', 'config.json', 'data/laboratory.sqlite3'):
                self.assertFalse((target / filename).exists())
            for source in (target / 'sandbox').glob('*.py'):
                ast.parse(source.read_text(encoding='utf-8'))

    def test_bundle_rejects_corrupted_checksum(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(cli.hashlib, 'sha256') as checksum:
                checksum.return_value.hexdigest.return_value = 'invalid'
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    cli.unpack(Path(temporary))

    def test_missing_installation_is_actionable(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, 'install first'):
                cli.setup(Path(temporary))

    def test_optional_prompt_defaults_and_accepts_explicit_yes(self):
        for response, expected in (('', False), ('no', False), ('YES', True), ('y', True)):
            with patch('builtins.input', return_value=response):
                self.assertEqual(cli.question('Optional libraries?'), expected)

    def test_port_bounds_fail_before_starting_process(self):
        with patch.object(cli, 'service') as service:
            for port in ('0', '65536'):
                with self.assertRaises(SystemExit):
                    cli.main(['start', '--port', port])
            service.assert_not_called()

    def test_environment_selects_distinct_home(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(cli.os.environ, {'TGAP_HOME': temporary}):
                self.assertEqual(cli.home_path(), Path(temporary).resolve())


class LauncherRegistrationTests(unittest.TestCase):
    ''' `tgap` must become usable on any system, and registering it must
    never break an installation. Every test uses a fake home folder. '''

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fake = Path(self.temporary.name)
        self.home = self.fake / '.tgap'
        (self.home / '.venv').mkdir(parents=True)
        patcher = patch.object(cli.Path, 'home', return_value=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.temporary.cleanup)

    def _path(self, *directories):
        return patch.dict(cli.os.environ, {'PATH': cli.os.pathsep.join(
            [str(d) for d in directories] + ['/usr/bin'])})

    @unittest.skipIf(cli.os.name == 'nt', 'POSIX launcher layout')
    def test_works_now_when_a_path_folder_is_writable(self):
        local = self.fake / '.local' / 'bin'
        with self._path(local):
            report = cli.register_launcher(self.home)
        self.assertTrue(report['works_now'])
        self.assertTrue((local / 'tgap').exists())
        self.assertFalse((self.fake / '.profile').exists(),
                         'no startup file should change when PATH already works')

    @unittest.skipIf(cli.os.name == 'nt', 'POSIX launcher layout')
    def test_new_terminals_get_the_folder_once(self):
        (self.fake / '.bashrc').write_text('# mine\n')
        with self._path():
            first = cli.register_launcher(self.home)
            cli.register_launcher(self.home)          # again: no duplicate
        self.assertFalse(first['works_now'])
        self.assertTrue(first['new_terminal'])
        for name in ('.profile', '.bashrc'):
            text = (self.fake / name).read_text()
            self.assertEqual(text.count(cli.SHELL_MARKER), 1, name)
        self.assertIn('# mine', (self.fake / '.bashrc').read_text())

    @unittest.skipIf(cli.os.name == 'nt', 'POSIX launcher layout')
    def test_another_programs_tgap_is_never_overwritten(self):
        local = self.fake / '.local' / 'bin'
        local.mkdir(parents=True)
        (local / 'tgap').write_text('#!/bin/sh\necho someone else\n')
        with self._path(local):
            report = cli.register_launcher(self.home)
        self.assertIn('someone else', (local / 'tgap').read_text())
        self.assertTrue(any('another program' in p for p in report['problems']))

    def test_windows_shortcut_works_at_once_and_registry_failure_is_harmless(self):
        apps = self.fake / 'AppData' / 'Local' / 'Microsoft' / 'WindowsApps'
        apps.mkdir(parents=True)
        def blocked(_directory):
            raise PermissionError('registry write blocked by policy')
        with patch.object(cli, '_is_windows', lambda: True), \
                patch.dict(cli.os.environ, {
                    'LOCALAPPDATA': str(self.fake / 'AppData' / 'Local'),
                    'PATH': cli.os.pathsep.join([str(apps), '/usr/bin'])}), \
                patch.object(cli, '_windows_user_path_add', blocked):
            report = cli.register_launcher(self.home)
        shortcut = apps / 'tgap.cmd'
        self.assertTrue(shortcut.exists())
        self.assertIn('tgap_cli', shortcut.read_text())
        self.assertTrue(report['works_now'])
        self.assertTrue(any('user PATH' in p for p in report['problems']))

    def test_windows_without_windowsapps_falls_back_to_the_registry(self):
        added = []
        with patch.object(cli, '_is_windows', lambda: True), \
                patch.dict(cli.os.environ, {
                    'LOCALAPPDATA': str(self.fake / 'nowhere'),
                    'PATH': '/usr/bin'}), \
                patch.object(cli, '_windows_user_path_add',
                             lambda d: added.append(d) or True):
            report = cli.register_launcher(self.home)
        self.assertEqual(added, [self.home / 'bin'])
        self.assertTrue(report['new_terminal'])
        self.assertTrue(report['launcher'].endswith('tgap.cmd'))

    def test_a_registration_crash_never_fails_the_install(self):
        source = cli.install.__code__.co_consts
        text = ' '.join(c for c in source if isinstance(c, str))
        self.assertIn('could not register the tgap command', text)


class RunPyWorkbenchCommandsTests(unittest.TestCase):
    ''' `python run.py start|stop|status` work with no PATH at all. '''

    def test_start_installs_first_when_needed(self):
        import runpy
        runner = runpy.run_path(str(Path(cli.__file__).resolve().parents[1]
                                    / 'run.py'), run_name='run_under_test')
        calls = []
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(runner['subprocess'], 'call',
                             lambda args, **_: calls.append(args) or 0):
            runner['workbench'](['start', '--home', temporary, '--no-browser'])
        self.assertEqual(calls[0][-2:], ['install', '--yes'])
        self.assertEqual(calls[1][-2:], ['start', '--no-browser'])
        self.assertIn('--home', calls[0])


if __name__ == '__main__':
    unittest.main()
