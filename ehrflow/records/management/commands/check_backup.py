from pathlib import Path
import sqlite3
import tempfile
from urllib.parse import quote

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Restore a backup to a disposable database and verify integrity and core record counts."

    def add_arguments(self, parser):
        parser.add_argument("backup")

    def handle(self, *args, **options):
        source = Path(options["backup"]).resolve()
        if not source.is_file():
            raise CommandError("Backup does not exist.")
        try:
            with tempfile.TemporaryDirectory(prefix="ehrflow-restore-") as temp:
                with sqlite3.connect(f"file:{quote(str(source))}?mode=ro", uri=True) as backup:
                    with sqlite3.connect(Path(temp) / "restored.sqlite3") as restored:
                        backup.backup(restored)
                        if restored.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                            raise CommandError("Restored database failed its integrity check.")
                        for table in ["records_patient", "records_encounter", "records_clinicalnote", "records_auditevent"]:
                            count = restored.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                            self.stdout.write(f"{table}: {count}")
        except sqlite3.Error as exc:
            raise CommandError(f"Restore verification failed: {exc}")
        self.stdout.write("Restore verified in a disposable database; the live database was not changed.")
