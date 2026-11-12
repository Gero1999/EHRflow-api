import logging
import uuid

from django.db import DatabaseError
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.response import Response

from .models import AuditEvent, StaffProfile

logger = logging.getLogger(__name__)


class AuditUnavailable(APIException):
    status_code = 503
    default_detail = "Audit service unavailable. No record data was released or changed."


class Conflict(APIException):
    status_code = 409
    default_detail = "The record changed. Refresh and try again."


def emit(profile, action, resource_type="workspace", resource_id="", outcome="allowed", request=None):
    try:
        if request is not None and not hasattr(request, "audit_request_id"):
            request.audit_request_id = uuid.uuid4()
        return AuditEvent.objects.create(
            workspace=profile.workspace, actor_id_snapshot=profile.pk,
            actor_name=profile.display_name, role=profile.role, action=action,
            resource_type=resource_type, resource_id=str(resource_id)[:40], outcome=outcome,
            request_id=getattr(request, "audit_request_id", uuid.uuid4()),
        )
    except DatabaseError:
        # Avoid writing request bodies or query strings into logs.
        logger.error("Audit persistence unavailable")
        raise AuditUnavailable()


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    request = context.get("request")
    view = context.get("view")
    if response is not None and response.status_code in [400, 401, 403, 404, 409] and request:
        profile = getattr(request, "staff", None)
        if profile is None and request.user.is_authenticated:
            try:
                profile = request.user.staff_profile
            except StaffProfile.DoesNotExist:
                pass
        if profile:
            # DRF handles the exception after the mutation's atomic block rolls
            # back; the denial event is persisted independently of that block.
            try:
                emit(profile, f"{request.method.lower()}.{view.__class__.__name__}",
                     "request", getattr(view, "kwargs", {}).get("pk", ""),
                     "denied", request)
            except AuditUnavailable as audit_exc:
                return Response({"detail": str(audit_exc.detail)}, status=503)
    return response
