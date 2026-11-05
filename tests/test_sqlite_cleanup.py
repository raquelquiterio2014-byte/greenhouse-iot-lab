import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from greenhouse.core import Store
from greenhouse.device_client import Outbox


class ConnectionCleanupTests(unittest.TestCase):
    def test_store_and_outbox_close_connections_on_success_and_error(self):
        with TemporaryDirectory() as folder:
            for cls in (Store, Outbox):
                storage = cls(Path(folder) / (cls.__name__ + ".sqlite3"))
                with storage.connect() as db:
                    db.execute("SELECT 1")
                with self.assertRaises(sqlite3.ProgrammingError):
                    db.execute("SELECT 1")
                with self.assertRaisesRegex(RuntimeError, "rollback"):
                    with storage.connect() as db:
                        raise RuntimeError("rollback")
                with self.assertRaises(sqlite3.ProgrammingError):
                    db.execute("SELECT 1")
