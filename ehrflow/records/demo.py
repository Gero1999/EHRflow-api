from datetime import timedelta
import secrets

from django.contrib.auth import get_user_model, login, logout
from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from .audit import emit
from .models import CareAssignment, ClinicalNote, DemoWorkspace, Encounter, Patient, StaffProfile
from .scenarios import NOTES, PATIENTS, PERSONAS
from .serializers import StaffSerializer, StrictSerializer


class DemoThrottle(SimpleRateThrottle):
    scope = "demo"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


@transaction.atomic
def create_workspace():
    now = timezone.now()
    workspace = DemoWorkspace.objects.create(expires_at=now + timedelta(hours=24))
    staff = {}
    for persona, (name, role) in PERSONAS.items():
        user = get_user_model().objects.create_user(username=f"{workspace.pk.hex}_{persona}")
        staff[persona] = StaffProfile.objects.create(user=user, workspace=workspace, persona=persona, display_name=name, role=role)
    patients = {key: Patient.objects.create(workspace=workspace, scenario=key, **PATIENTS[key]) for key in ["maya", "jonah", "avery"]}
    for key, delta, clinician in [("maya", 0, "clinician"), ("jonah", 1, "other_clinician")]:
        encounter = Encounter.objects.create(patient=patients[key], reason="follow_up", scheduled_at=now + timedelta(hours=delta))
        for persona in [clinician] + (["nurse"] if key == "maya" else []):
            CareAssignment.objects.create(encounter=encounter, staff=staff[persona], starts_at=now)
    emit(staff["registrar"], "workspace.created")
    return workspace


def workspace_payload(workspace, profile):
    return {
        "workspace": str(workspace.pk), "expires_at": workspace.expires_at,
        "user": StaffSerializer(profile).data,
        "personas": StaffSerializer(workspace.staff.filter(user__is_active=True), many=True).data,
        "synthetic_only": True,
    }


def demo_workspace(request):
    # A token or a client-supplied workspace ID cannot create switch rights.
    key = request.session.get("demo_workspace")
    if not key or not request.user.is_authenticated:
        raise PermissionDenied("Start a demo session first.")
    try:
        workspace = DemoWorkspace.objects.get(pk=key, expires_at__gt=timezone.now())
        if request.user.staff_profile.workspace_id != workspace.pk:
            raise PermissionDenied("Demo session mismatch.")
        return workspace
    except (DemoWorkspace.DoesNotExist, StaffProfile.DoesNotExist):
        raise PermissionDenied("Demo session expired. Start a new session.")


def assume_persona(request, workspace, profile):
    login(request._request, profile.user, backend="django.contrib.auth.backends.ModelBackend")
    request.session["demo_workspace"] = str(workspace.pk)
    request.session.set_expiry(1800)


@method_decorator(csrf_protect, name="dispatch")
class DemoStart(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [DemoThrottle]

    def post(self, request):
        data = StrictSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        # Only server-side sessions confer ownership of an existing workspace.
        existing = request.session.get("demo_workspace")
        workspace = DemoWorkspace.objects.filter(pk=existing, expires_at__gt=timezone.now()).first() if existing else None
        if workspace is None:
            workspace = create_workspace()
        profile = workspace.staff.get(persona="registrar")
        if not profile.user.is_active:
            profile = workspace.staff.get(persona="access_admin")
        assume_persona(request, workspace, profile)
        return Response(workspace_payload(workspace, profile), status=201)


class PersonaInput(StrictSerializer):
    persona = serializers.CharField(max_length=30)


@method_decorator(csrf_protect, name="dispatch")
class DemoSwitch(APIView):
    throttle_classes = [DemoThrottle]

    @transaction.atomic
    def post(self, request):
        workspace = demo_workspace(request)
        data = PersonaInput(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            target = workspace.staff.select_related("user").get(persona=data.validated_data["persona"], user__is_active=True)
        except StaffProfile.DoesNotExist:
            raise NotFound("Demo persona not available.")
        emit(request.staff, "demo.persona_switch", "staff", target.pk, request=request)
        assume_persona(request, workspace, target)
        return Response(workspace_payload(workspace, target))


@method_decorator(csrf_protect, name="dispatch")
class DemoReset(APIView):
    throttle_classes = [DemoThrottle]

    @transaction.atomic
    def post(self, request):
        old = demo_workspace(request)
        data = StrictSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        workspace = create_workspace()
        profile = workspace.staff.get(persona="registrar")
        emit(request.staff, "workspace.reset", request=request)
        # Invalidate the old workspace for sessions and tokens; cleanup is an
        # explicit management task so existing audit history isn't overwritten.
        old.expires_at = timezone.now()
        old.save(update_fields=["expires_at"])
        assume_persona(request, workspace, profile)
        return Response(workspace_payload(workspace, profile), status=201)


@method_decorator(csrf_protect, name="dispatch")
class DemoLogout(APIView):
    def post(self, request):
        emit(request.staff, "session.logout", request=request)
        logout(request._request)
        return Response({"detail": "Signed out."})
