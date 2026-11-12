import uuid
from django.conf import settings
from django.db import models

class Role(models.TextChoices):
    REGISTRAR = "registrar", "Registrar"
    NURSE = "nurse", "Nurse"
    CLINICIAN = "clinician", "Clinician"
    REVIEWER = "reviewer", "Privacy reviewer"
    ADMIN = "access_admin", "Access administrator"


class DemoWorkspace(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()


class StaffProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_profile")
    workspace = models.ForeignKey(DemoWorkspace, on_delete=models.CASCADE, related_name="staff")
    persona = models.CharField(max_length=30)
    display_name = models.CharField(max_length=80)
    role = models.CharField(max_length=20, choices=Role.choices)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace", "persona"], name="unique_workspace_persona")]
        ordering = ["id"]


class Patient(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(DemoWorkspace, on_delete=models.CASCADE, related_name="patients")
    scenario = models.CharField(max_length=30)
    record_number = models.CharField(max_length=20)
    name = models.CharField(max_length=100, db_index=True)
    date_of_birth = models.DateField()
    contact_email = models.EmailField()
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [models.UniqueConstraint(fields=["workspace", "scenario"], name="unique_patient_scenario")]


class Encounter(models.Model):
    class State(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="encounters")
    reason = models.CharField(max_length=30)
    scheduled_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=State.choices, default=State.SCHEDULED)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-scheduled_at", "id"]


class CareAssignment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="assignments")
    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name="assignments")
    active = models.BooleanField(default=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["encounter", "staff"], name="unique_encounter_staff")]


class Observation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="observations")
    author = models.ForeignKey(StaffProfile, on_delete=models.PROTECT)
    kind = models.CharField(max_length=30)
    value = models.DecimalField(max_digits=6, decimal_places=2)
    unit = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "id"]


class ClinicalNote(models.Model):
    class State(models.TextChoices):
        DRAFT = "draft", "Draft"
        FINALIZED = "finalized", "Finalized"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(StaffProfile, on_delete=models.PROTECT)
    template = models.CharField(max_length=30)
    body = models.TextField()
    status = models.CharField(max_length=20, choices=State.choices, default=State.DRAFT)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "id"]


class NoteAddendum(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    note = models.ForeignKey(ClinicalNote, on_delete=models.CASCADE, related_name="addenda")
    author = models.ForeignKey(StaffProfile, on_delete=models.PROTECT)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class AuditEvent(models.Model):
    workspace = models.ForeignKey(DemoWorkspace, on_delete=models.CASCADE, related_name="events")
    actor_id_snapshot = models.PositiveBigIntegerField(null=True)
    actor_name = models.CharField(max_length=80)
    role = models.CharField(max_length=20)
    action = models.CharField(max_length=80)
    resource_type = models.CharField(max_length=30)
    resource_id = models.CharField(max_length=40, blank=True)
    outcome = models.CharField(max_length=20)
    request_id = models.UUIDField(default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
