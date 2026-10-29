import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from legal_service.db import connection


class DataPermissionsTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "POSIX file modes are unavailable on Windows")
    def test_database_and_directory_are_private(self):
        with tempfile.TemporaryDirectory() as root:
            data_dir = Path(root) / "data"
            with patch.dict(os.environ, {"APP_DATA_DIR": str(data_dir)}):
                with connection() as con:
                    con.execute("CREATE TABLE private_test(value TEXT)")
                self.assertEqual(stat.S_IMODE(data_dir.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE((data_dir / "legal.sqlite3").stat().st_mode), 0o600)
