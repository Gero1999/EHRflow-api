from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, NotFound, PermissionDenied
from rest_framework.permissions import BasePermission

from .models import CareAssignment, Encounter, Patient, Role, StaffProfile


class HasWorkspace(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated or not request.user.is_active:
            return False
        try:
            # Re-read role, account status, and workspace expiry on every
            # request, including when a caller holds a cached User instance.
            profile = StaffProfile.objects.select_related("workspace", "user").get(user_id=request.user.pk, user__is_active=True)
        except StaffProfile.DoesNotExist:
            return False
        if profile.workspace.expires_at <= timezone.now():
            raise AuthenticationFailed("Demo workspace expired. Start a fresh session.")
        request.staff = profile
        return True


def require_role(request, *roles):
    if request.staff.role not in roles:
        raise PermissionDenied("Your role does not permit this action.")


def active_assignments(profile):
    now = timezone.now()
    if profile.role not in [Role.NURSE, Role.CLINICIAN]:
        return CareAssignment.objects.none()
    return CareAssignment.objects.filter(
        staff=profile, active=True, starts_at__lte=now,
        encounter__patient__workspace=profile.workspace,
    ).filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))


def visible_patients(profile):
    patients = Patient.objects.filter(workspace=profile.workspace)
    if profile.role == Role.REGISTRAR:
        return patients
    if profile.role in [Role.NURSE, Role.CLINICIAN]:
        return patients.filter(encounters__assignments__in=active_assignments(profile)).distinct()
    return patients.none()


def visible_encounters(profile):
    encounters = Encounter.objects.filter(patient__workspace=profile.workspace).select_related("patient")
    if profile.role == Role.REGISTRAR:
        return encounters
    return encounters.filter(assignments__in=active_assignments(profile)).distinct()


def get_encounter(request, pk, lock=False):
    queryset = visible_encounters(request.staff)
    if lock:
        queryset = queryset.select_for_update()
    try:
        return queryset.get(pk=pk)
    except Encounter.DoesNotExist:
        raise NotFound("Record not available.")
