from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.cache import never_cache
from djoser.views import TokenCreateView
from rest_framework import generics, serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import AuthenticationFailed, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import serializers as s
from .audit import Conflict, emit
from .authentication import LoginThrottle
from .filters import EncounterFilter
from .demo import workspace_payload
from .models import AuditEvent, CareAssignment, ClinicalNote, Encounter, NoteAddendum, Observation, Patient, Role, StaffProfile
from .permissions import active_assignments, get_encounter, require_role, visible_encounters, visible_patients
from .scenarios import ADDENDA, NOTES, OBSERVATIONS, PATIENTS


@never_cache
@ensure_csrf_cookie
def index(request):
    return render(request, "records/index.html")


def validate(serializer_class, data):
    serializer = serializer_class(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def check_version(obj, data):
    if obj.version != data["version"]:
        raise Conflict()


class Me(APIView):
    def get(self, request):
        return Response(workspace_payload(request.staff.workspace, request.staff))


class TokenLogin(TokenCreateView):
    permission_classes = [AllowAny]
    serializer_class = s.LoginSerializer
    throttle_classes = [LoginThrottle]

    @transaction.atomic
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            if any(error.code == "invalid_credentials" for error in serializer.errors.get("non_field_errors", [])):
                raise AuthenticationFailed("Invalid credentials.")
            raise ValidationError(serializer.errors)
        try:
            profile = serializer.user.staff_profile
        except StaffProfile.DoesNotExist:
            raise AuthenticationFailed("No EHR staff access.")
        if profile.workspace.expires_at <= timezone.now():
            raise AuthenticationFailed("Workspace expired.")
        # A new login replaces previous tokens. Demo accounts have unusable
        # passwords; local provision_staff explicitly enables credential login.
        Token.objects.filter(user=serializer.user).delete()
        token = Token.objects.create(user=serializer.user)
        emit(profile, "token.login", request=request)
        return Response({"auth_token": token.key, "expires_in": 1800}, status=201)


class TokenLogout(APIView):
    def post(self, request):
        emit(request.staff, "token.logout", request=request)
        Token.objects.filter(user=request.user).delete()
        return Response({"detail": "API token revoked."})


class AuditedListMixin:
    audit_action = "list"

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        emit(request.staff, self.audit_action, "collection", request=request)
        return response


class PatientList(AuditedListMixin, generics.ListCreateAPIView):
    serializer_class = s.PatientSerializer
    search_fields = ["name", "record_number"]
    filterset_fields = ["scenario"]
    ordering_fields = ["name", "record_number"]
    ordering = ["name", "id"]
    audit_action = "patients.list"

    def get_queryset(self):
        require_role(self.request, Role.REGISTRAR, Role.NURSE, Role.CLINICIAN)
        return visible_patients(self.request.staff)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        require_role(request, Role.REGISTRAR)
        data = validate(s.PatientCreate, request.data)
        if Patient.objects.filter(workspace=request.staff.workspace, scenario=data["scenario"]).exists():
            raise Conflict("This synthetic patient is already registered.")
        patient = Patient.objects.create(workspace=request.staff.workspace, scenario=data["scenario"], **PATIENTS[data["scenario"]])
        emit(request.staff, "patient.registered", "patient", patient.pk, request=request)
        return Response(s.PatientSerializer(patient).data, status=201)


class PatientDetail(APIView):
    def get(self, request, pk):
        require_role(request, Role.REGISTRAR, Role.NURSE, Role.CLINICIAN)
        patient = get_object_or_404(visible_patients(request.staff), pk=pk)
        emit(request.staff, "patient.read", "patient", pk, request=request)
        return Response(s.PatientSerializer(patient).data)

    @transaction.atomic
    def patch(self, request, pk):
        require_role(request, Role.REGISTRAR)
        patient = get_object_or_404(visible_patients(request.staff).select_for_update(), pk=pk)
        data = validate(s.PatientUpdate, request.data)
        check_version(patient, data)
        suffix = "+alternate" if data["contact"] == "alternate" else ""
        mailbox, domain = PATIENTS[patient.scenario]["contact_email"].split("@")
        patient.contact_email = f"{mailbox}{suffix}@{domain}"
        patient.version += 1
        patient.save(update_fields=["contact_email", "version"])
        emit(request.staff, "patient.contact_updated", "patient", pk, request=request)
        return Response(s.PatientSerializer(patient).data)


class EncounterList(AuditedListMixin, generics.ListCreateAPIView):
    serializer_class = s.EncounterSerializer
    filterset_class = EncounterFilter
    search_fields = ["patient__name", "patient__record_number"]
    ordering_fields = ["scheduled_at", "status"]
    ordering = ["scheduled_at", "id"]
    audit_action = "encounters.list"

    def get_queryset(self):
        require_role(self.request, Role.REGISTRAR, Role.NURSE, Role.CLINICIAN)
        return visible_encounters(self.request.staff).prefetch_related("assignments__staff")

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        require_role(request, Role.REGISTRAR)
        data = validate(s.EncounterCreate, request.data)
        patient = get_object_or_404(Patient, pk=data["patient"], workspace=request.staff.workspace)
        if patient.encounters.exclude(status=Encounter.State.COMPLETED).exists():
            raise Conflict("This patient already has an open encounter.")
        encounter = Encounter.objects.create(patient=patient, reason=data["reason"], scheduled_at=timezone.now())
        emit(request.staff, "encounter.scheduled", "encounter", encounter.pk, request=request)
        return Response(s.EncounterSerializer(encounter).data, status=201)


class EncounterDetail(APIView):
    def get(self, request, pk):
        require_role(request, Role.REGISTRAR, Role.NURSE, Role.CLINICIAN)
        encounter = get_encounter(request, pk)
        emit(request.staff, "encounter.read", "encounter", pk, request=request)
        return Response(s.EncounterSerializer(encounter).data)


class AssignmentList(APIView):
    @transaction.atomic
    def post(self, request):
        require_role(request, Role.REGISTRAR)
        data = validate(s.AssignmentCreate, request.data)
        encounter = get_encounter(request, data["encounter"], lock=True)
        if encounter.status == Encounter.State.COMPLETED:
            raise Conflict("A completed encounter cannot receive a new care assignment.")
        staff = get_object_or_404(StaffProfile, pk=data["staff"], workspace=request.staff.workspace, user__is_active=True, role__in=[Role.NURSE, Role.CLINICIAN])
        existing = CareAssignment.objects.filter(encounter=encounter, staff=staff).first()
        if existing and existing.active:
            raise Conflict("This staff member is already assigned.")
        assignment, _ = CareAssignment.objects.update_or_create(encounter=encounter, staff=staff, defaults={"starts_at": timezone.now(), "ends_at": None, "active": True})
        emit(request.staff, "care.assigned", "assignment", assignment.pk, request=request)
        return Response(s.EncounterSerializer(encounter).data, status=201)


class AssignmentDetail(APIView):
    @transaction.atomic
    def delete(self, request, pk):
        require_role(request, Role.REGISTRAR)
        assignment = get_object_or_404(CareAssignment.objects.select_for_update(), pk=pk, encounter__patient__workspace=request.staff.workspace)
        assignment.active = False
        assignment.ends_at = timezone.now()
        assignment.save(update_fields=["active", "ends_at"])
        emit(request.staff, "care.revoked", "assignment", pk, request=request)
        return Response({"detail": "Care assignment revoked."})


class ClinicalRead(APIView):
    def get(self, request, pk):
        require_role(request, Role.NURSE, Role.CLINICIAN)
        encounter = get_encounter(request, pk)
        observations = s.ObservationSerializer(encounter.observations.select_related("author"), many=True).data
        notes = encounter.notes.select_related("author").prefetch_related("addenda__author")
        if request.staff.role == Role.CLINICIAN:
            notes = notes.filter(Q(status=ClinicalNote.State.FINALIZED) | Q(author=request.staff))
            note_data = s.NoteSerializer(notes, many=True).data
        else:
            # Nurses receive finalized summary metadata, not full notes/drafts.
            note_data = [{"id": str(n.pk), "status": n.status, "author_name": n.author.display_name, "summary": "Finalized synthetic visit documentation available to the clinician.", "finalized_at": n.finalized_at} for n in notes.filter(status=ClinicalNote.State.FINALIZED)]
        emit(request.staff, "chart.read", "encounter", pk, request=request)
        return Response({"encounter": s.EncounterSerializer(encounter).data, "observations": observations, "notes": note_data})


class ObservationList(APIView):
    @transaction.atomic
    def post(self, request, pk):
        require_role(request, Role.NURSE, Role.CLINICIAN)
        encounter = get_encounter(request, pk, lock=True)
        if encounter.status == Encounter.State.COMPLETED:
            raise Conflict("This encounter is completed.")
        data = validate(s.ObservationCreate, request.data)
        value, unit = OBSERVATIONS[data["kind"]]
        observation = Observation.objects.create(encounter=encounter, author=request.staff, kind=data["kind"], value=value, unit=unit)
        encounter.status = Encounter.State.IN_PROGRESS
        encounter.version += 1
        encounter.save(update_fields=["status", "version"])
        emit(request.staff, "observation.recorded", "observation", observation.pk, request=request)
        return Response(s.ObservationSerializer(observation).data, status=201)


class NoteList(APIView):
    @transaction.atomic
    def post(self, request, pk):
        require_role(request, Role.CLINICIAN)
        encounter = get_encounter(request, pk, lock=True)
        if encounter.status == Encounter.State.COMPLETED:
            raise Conflict("This encounter is completed.")
        data = validate(s.NoteCreate, request.data)
        if encounter.notes.filter(author=request.staff, status=ClinicalNote.State.DRAFT).exists():
            raise Conflict("Edit your existing draft before creating another.")
        note = ClinicalNote.objects.create(encounter=encounter, author=request.staff, template=data["template"], body=NOTES[data["template"]])
        emit(request.staff, "note.drafted", "note", note.pk, request=request)
        return Response(s.NoteSerializer(note).data, status=201)


def own_note(request, pk):
    require_role(request, Role.CLINICIAN)
    note = get_object_or_404(ClinicalNote.objects.select_for_update().select_related("encounter__patient"), pk=pk, encounter__in=visible_encounters(request.staff))
    if note.author_id != request.staff.pk:
        raise PermissionDenied("Only the note's author may modify it.")
    return note


class NoteDetail(APIView):
    @transaction.atomic
    def patch(self, request, pk):
        note = own_note(request, pk)
        data = validate(s.NoteUpdate, request.data)
        check_version(note, data)
        if note.status != ClinicalNote.State.DRAFT:
            raise Conflict("Finalized content is immutable. Add an addendum instead.")
        note.template, note.body = data["template"], NOTES[data["template"]]
        note.version += 1
        note.save(update_fields=["template", "body", "version"])
        emit(request.staff, "note.updated", "note", pk, request=request)
        return Response(s.NoteSerializer(note).data)


class NoteFinalize(APIView):
    @transaction.atomic
    def post(self, request, pk):
        note = own_note(request, pk)
        data = validate(s.VersionInput, request.data)
        check_version(note, data)
        if note.status != ClinicalNote.State.DRAFT:
            raise Conflict("This note is already finalized.")
        note.status = ClinicalNote.State.FINALIZED
        note.finalized_at = timezone.now()
        note.version += 1
        note.save(update_fields=["status", "finalized_at", "version"])
        emit(request.staff, "note.finalized", "note", pk, request=request)
        return Response(s.NoteSerializer(note).data)


class AddendumList(APIView):
    @transaction.atomic
    def post(self, request, pk):
        note = own_note(request, pk)
        data = validate(s.AddendumInput, request.data)
        check_version(note, data)
        if note.status != ClinicalNote.State.FINALIZED:
            raise Conflict("Finalize the note before adding an addendum.")
        addendum = NoteAddendum.objects.create(note=note, author=request.staff, body=ADDENDA[data["template"]])
        note.version += 1
        note.save(update_fields=["version"])
        emit(request.staff, "note.addendum_created", "note", pk, request=request)
        return Response(s.AddendumSerializer(addendum).data, status=201)


class EncounterComplete(APIView):
    @transaction.atomic
    def post(self, request, pk):
        require_role(request, Role.CLINICIAN)
        encounter = get_encounter(request, pk, lock=True)
        data = validate(s.VersionInput, request.data)
        check_version(encounter, data)
        if encounter.status == Encounter.State.COMPLETED:
            raise Conflict("Encounter already completed.")
        if encounter.notes.filter(status=ClinicalNote.State.DRAFT).exists() or not encounter.notes.filter(status=ClinicalNote.State.FINALIZED).exists():
            raise Conflict("Finalize encounter notes before completing the visit.")
        encounter.status = Encounter.State.COMPLETED
        encounter.version += 1
        encounter.save(update_fields=["status", "version"])
        emit(request.staff, "encounter.completed", "encounter", pk, request=request)
        return Response(s.EncounterSerializer(encounter).data)


class StaffList(APIView):
    def get(self, request):
        require_role(request, Role.REGISTRAR, Role.ADMIN)
        queryset = StaffProfile.objects.filter(workspace=request.staff.workspace).select_related("user")
        if request.staff.role == Role.REGISTRAR:
            queryset = queryset.filter(role__in=[Role.NURSE, Role.CLINICIAN], user__is_active=True)
        emit(request.staff, "staff.list", "staff", request=request)
        return Response(s.StaffSerializer(queryset, many=True).data)

    @transaction.atomic
    def post(self, request):
        require_role(request, Role.ADMIN)
        data = validate(s.StaffCreate, request.data)
        workspace = request.staff.workspace
        if workspace.staff.filter(persona="trainee").exists():
            raise Conflict("The synthetic trainee is already provisioned.")
        user = get_user_model().objects.create_user(username=f"{workspace.pk.hex}_trainee")
        profile = StaffProfile.objects.create(user=user, workspace=workspace, persona="trainee", display_name="Trainee One", role=data["role"])
        emit(request.staff, "staff.provisioned", "staff", profile.pk, request=request)
        return Response(s.StaffSerializer(profile).data, status=201)


class StaffDetail(APIView):
    @transaction.atomic
    def patch(self, request, pk):
        require_role(request, Role.ADMIN)
        target = get_object_or_404(StaffProfile.objects.select_for_update(), pk=pk, workspace=request.staff.workspace)
        if target.pk == request.staff.pk or target.role == Role.ADMIN:
            raise PermissionDenied("The demo access-administrator account is protected.")
        data = validate(s.StaffUpdate, request.data)
        if "role" in data and data["role"] != target.role:
            target.role = data["role"]
            target.save(update_fields=["role"])
            target.assignments.update(active=False, ends_at=timezone.now())
        if "active" in data:
            target.user.is_active = data["active"]
            target.user.save(update_fields=["is_active"])
            if not data["active"]:
                Token.objects.filter(user=target.user).delete()
                target.assignments.update(active=False, ends_at=timezone.now())
        emit(request.staff, "staff.access_changed", "staff", target.pk, request=request)
        return Response(s.StaffSerializer(target).data)


class AuditList(AuditedListMixin, generics.ListAPIView):
    serializer_class = s.AuditSerializer
    filterset_fields = ["outcome", "role", "action"]
    ordering_fields = ["created_at"]
    ordering = ["-created_at", "-id"]
    audit_action = "audit.reviewed"

    def get_queryset(self):
        require_role(self.request, Role.REVIEWER)
        return AuditEvent.objects.filter(workspace=self.request.staff.workspace)
