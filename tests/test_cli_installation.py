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


if __name__ == '__main__':
    unittest.main()
