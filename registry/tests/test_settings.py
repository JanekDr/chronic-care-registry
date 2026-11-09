import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from django.conf import settings
from django.test import SimpleTestCase
from django.utils.crypto import get_random_string


class EnvironmentSettingsTests(SimpleTestCase):
    def check_settings(self, environment, assertion=""):
        return subprocess.run(
            [sys.executable, "-c", "import config.settings as s; " + (assertion or "pass")],
            cwd=settings.BASE_DIR,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_startup_requires_secret_key_from_environment(self):
        environment = os.environ.copy()
        environment.pop("SECRET_KEY", None)
        result = self.check_settings(environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Ustaw zmienną środowiskową SECRET_KEY", result.stderr)

    def test_sqlite_path_is_configurable_and_debug_is_disabled_by_default(self):
        environment = os.environ.copy()
        environment["SECRET_KEY"] = get_random_string(64)
        environment.pop("DEBUG", None)
        with TemporaryDirectory() as directory:
            environment["DATABASE_PATH"] = str(Path(directory) / "registry.sqlite3")
            result = self.check_settings(
                environment,
                "import os; assert str(s.DATABASES['default']['NAME']) == os.environ['DATABASE_PATH']; assert not s.DEBUG",
            )
        self.assertEqual(result.returncode, 0, result.stderr)
