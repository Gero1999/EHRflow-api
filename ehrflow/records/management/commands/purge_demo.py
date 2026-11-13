from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from records.models import DemoWorkspace


class Command(BaseCommand):
    help = "Delete expired synthetic workspaces, their records/audit history, and demo users."

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true", help="Delete expired workspaces; otherwise only report counts.")

    @transaction.atomic
    def handle(self, *args, **options):
        workspaces = DemoWorkspace.objects.filter(expires_at__lte=timezone.now())
        count = workspaces.count()
        if not options["execute"]:
            self.stdout.write(f"{count} expired synthetic workspaces. Use --execute to purge their data and audit history.")
            return
        users = list(get_user_model().objects.filter(staff_profile__workspace__in=workspaces).values_list("id", flat=True))
        # Remove encounter content first: clinical author foreign keys use
        # PROTECT to prevent accidental authorship loss during ordinary work.
        for workspace in workspaces:
            workspace.patients.all().delete()
            workspace.delete()
        get_user_model().objects.filter(id__in=users).delete()
        self.stdout.write(f"Purged {count} expired synthetic workspaces.")
