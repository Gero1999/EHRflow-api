from collections.abc import Mapping
from djoser.serializers import TokenCreateSerializer
from rest_framework import serializers

from .models import AuditEvent, ClinicalNote, Encounter, NoteAddendum, Observation, Patient, Role, StaffProfile
from .scenarios import ADDENDA, NOTES, OBSERVATIONS, PATIENTS, REASONS


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unexpected = set(data) - {key for key, field in self.fields.items() if not field.read_only}
            if unexpected:
                raise serializers.ValidationError({key: "This field cannot be supplied." for key in unexpected})
        return super().to_internal_value(data)


class LoginSerializer(TokenCreateSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = True
        self.fields["password"] = serializers.CharField(required=True, max_length=128, trim_whitespace=False, write_only=True)
        self.fields["username"] = serializers.CharField(required=True, max_length=150)


class PatientCreate(StrictSerializer):
    scenario = serializers.ChoiceField(choices=list(PATIENTS))


class PatientUpdate(StrictSerializer):
    version = serializers.IntegerField(min_value=1)
    contact = serializers.ChoiceField(choices=["primary", "alternate"])


class PatientSerializer(serializers.ModelSerializer):
    classification = serializers.SerializerMethodField()

    def get_classification(self, obj):
        return "Synthetic patient administration"

    class Meta:
        model = Patient
        fields = ["id", "record_number", "scenario", "name", "date_of_birth", "contact_email", "version", "classification"]


class EncounterCreate(StrictSerializer):
    patient = serializers.UUIDField()
    reason = serializers.ChoiceField(choices=list(REASONS))


class EncounterSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.name")
    record_number = serializers.CharField(source="patient.record_number")
    assignments = serializers.SerializerMethodField()
    reason_label = serializers.SerializerMethodField()

    def get_assignments(self, obj):
        return [{"id": str(a.pk), "staff": a.staff_id, "name": a.staff.display_name, "role": a.staff.role, "active": a.active} for a in obj.assignments.select_related("staff").all()]

    def get_reason_label(self, obj):
        return REASONS.get(obj.reason, obj.reason)

    class Meta:
        model = Encounter
        fields = ["id", "patient", "patient_name", "record_number", "reason", "reason_label", "scheduled_at", "status", "version", "assignments"]


class AssignmentCreate(StrictSerializer):
    encounter = serializers.UUIDField()
    staff = serializers.IntegerField(min_value=1)


class ObservationCreate(StrictSerializer):
    kind = serializers.ChoiceField(choices=list(OBSERVATIONS))


class ObservationSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.display_name")

    class Meta:
        model = Observation
        fields = ["id", "encounter", "kind", "value", "unit", "author_name", "created_at"]


class NoteCreate(StrictSerializer):
    template = serializers.ChoiceField(choices=list(NOTES))


class VersionInput(StrictSerializer):
    version = serializers.IntegerField(min_value=1)


class NoteUpdate(VersionInput):
    template = serializers.ChoiceField(choices=list(NOTES))


class AddendumInput(VersionInput):
    template = serializers.ChoiceField(choices=list(ADDENDA))


class AddendumSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.display_name")

    class Meta:
        model = NoteAddendum
        fields = ["id", "author_name", "body", "created_at"]


class NoteSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.display_name")
    addenda = AddendumSerializer(many=True)

    class Meta:
        model = ClinicalNote
        fields = ["id", "encounter", "author", "author_name", "template", "body", "status", "version", "created_at", "finalized_at", "addenda"]


class StaffSerializer(serializers.ModelSerializer):
    active = serializers.BooleanField(source="user.is_active")

    class Meta:
        model = StaffProfile
        fields = ["id", "persona", "display_name", "role", "active"]


class StaffCreate(StrictSerializer):
    role = serializers.ChoiceField(choices=[Role.REGISTRAR, Role.NURSE, Role.CLINICIAN, Role.REVIEWER])


class StaffUpdate(StrictSerializer):
    role = serializers.ChoiceField(choices=[Role.REGISTRAR, Role.NURSE, Role.CLINICIAN, Role.REVIEWER], required=False)
    active = serializers.BooleanField(required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Supply a role or active status.")
        return attrs


class AuditSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = ["id", "actor_name", "role", "action", "resource_type", "resource_id", "outcome", "request_id", "created_at"]
