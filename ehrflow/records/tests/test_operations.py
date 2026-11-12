from datetime import timedelta
from io import StringIO
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sqlite3
import tempfile

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.db import connection
from django.test import TransactionTestCase, SimpleTestCase
from django.utils import timezone

from records.demo import create_workspace
from records.middleware import RedactQueryFilter
from records.models import ClinicalNote, DemoWorkspace, Observation, StaffProfile
from records.scenarios import NOTES


class MaintenanceTests(TransactionTestCase):
    def test_backup_restores_populated_records_and_refuses_overwrite(self):
        workspace = create_workspace()
        patient = workspace.patients.get(scenario='maya')
        ClinicalNote.objects.create(encounter=patient.encounters.get(), author=workspace.staff.get(persona='clinician'), template='follow_up', body=NOTES['follow_up'])
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source.sqlite3'
            backup = Path(temp) / 'backup.sqlite3'
            # Snapshot the genuinely migrated test DB to a file; backup_demo is
            # intentionally restricted to file-backed SQLite installations.
            with sqlite3.connect(source) as db:
                connection.connection.backup(db)
            settings = SimpleNamespace(DATABASES={'default': {'NAME': source}})
            with patch('records.management.commands.backup_demo.settings', settings):
                call_command('backup_demo', str(backup), stdout=StringIO())
                with self.assertRaises(CommandError):
                    call_command('backup_demo', str(backup), stdout=StringIO())
            self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
            with sqlite3.connect(backup) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM records_patient').fetchone()[0], 3)
                self.assertEqual(db.execute('SELECT body FROM records_clinicalnote').fetchone()[0], NOTES['follow_up'])
            result = StringIO()
            call_command('check_backup', str(backup), stdout=result)
            self.assertIn('records_patient: 3', result.getvalue())
            self.assertIn('records_clinicalnote: 1', result.getvalue())
            self.assertIn('live database was not changed', result.getvalue())

    def test_purge_is_explicit_and_keeps_active_workspaces(self):
        old = create_workspace()
        current = create_workspace()
        encounter = old.patients.get(scenario='maya').encounters.get()
        ClinicalNote.objects.create(encounter=encounter, author=old.staff.get(persona='clinician'), template='follow_up', body=NOTES['follow_up'])
        Observation.objects.create(encounter=encounter, author=old.staff.get(persona='nurse'), kind='pulse', value=72, unit='bpm')
        old_user_ids = list(old.staff.values_list('user_id', flat=True))
        DemoWorkspace.objects.filter(pk=old.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        call_command('purge_demo', stdout=StringIO())
        self.assertTrue(DemoWorkspace.objects.filter(pk=old.pk).exists())
        call_command('purge_demo', execute=True, stdout=StringIO())
        self.assertFalse(DemoWorkspace.objects.filter(pk=old.pk).exists())
        self.assertFalse(get_user_model().objects.filter(pk__in=old_user_ids).exists())
        self.assertTrue(DemoWorkspace.objects.filter(pk=current.pk).exists())
        self.assertEqual(current.patients.count(), 3)
        self.assertEqual(current.staff.count(), 6)

    def test_staff_listing_has_no_passwords_and_rejects_invalid_ids(self):
        workspace = create_workspace()
        output = StringIO()
        call_command('demo_staff', workspace=str(workspace.pk), stdout=output)
        self.assertIn('clinician:', output.getvalue())
        self.assertIn('without passwords', output.getvalue())
        with self.assertRaises(CommandError):
            call_command('demo_staff', workspace='invalid', stdout=StringIO())


class LoggingTests(SimpleTestCase):
    def test_development_request_logging_redacts_query_values(self):
        record = logging.LogRecord('django.server', logging.INFO, '', 0, '"%s" %s %s', ('GET /api/patients?search=DO_NOT_LOG&scenario=maya HTTP/1.1', '200', '100'), None)
        RedactQueryFilter().filter(record)
        self.assertNotIn('DO_NOT_LOG', record.getMessage())
        self.assertIn('/api/patients?[redacted]', record.getMessage())
