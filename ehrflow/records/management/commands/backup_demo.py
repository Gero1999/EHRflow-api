import os
from pathlib import Path
import sqlite3
from urllib.parse import quote

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a consistent local SQLite backup of synthetic demo data (no overwrite)."

    def add_arguments(self, parser):
        parser.add_argument("output", help="Destination .sqlite3 file, kept private and outside version control.")

    def handle(self, *args, **options):
        source = Path(settings.DATABASES["default"]["NAME"]).resolve()
        target = Path(options["output"]).resolve()
        if target == source or not source.is_file():
            raise CommandError("Migrate the source database and choose a different backup path.")
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except FileExistsError:
            raise CommandError("Backup file already exists. Choose a new path.")
        try:
            with sqlite3.connect(f"file:{quote(str(source))}?mode=ro", uri=True) as original:
                with sqlite3.connect(target) as backup:
                    original.backup(backup)
        except sqlite3.Error as exc:
            raise CommandError(f"Backup failed: {exc}")
        self.stdout.write(f"Backup saved: {target}")
