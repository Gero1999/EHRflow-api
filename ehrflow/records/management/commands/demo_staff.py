from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from django.utils import timezone
from records.models import DemoWorkspace


class Command(BaseCommand):
    help = "List local demo staff usernames for optional token-authentication exercises."

    def add_arguments(self, parser):
        parser.add_argument("--workspace", required=True)

    def handle(self, *args, **options):
        try:
            workspace = DemoWorkspace.objects.get(pk=options["workspace"], expires_at__gt=timezone.now())
        except (DemoWorkspace.DoesNotExist, ValueError, ValidationError):
            raise CommandError("Active workspace not found.")
        for profile in workspace.staff.select_related("user"):
            self.stdout.write(f"{profile.persona}: {profile.user.username} ({profile.role})")
        self.stdout.write("Demo accounts start without passwords. Use changepassword to explicitly enable local token login.")
