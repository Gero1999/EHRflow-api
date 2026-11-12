from django_filters import rest_framework as filters
from .models import Encounter


class EncounterFilter(filters.FilterSet):
    # A UUID filter must not validate existence against an unscoped global
    # Patient queryset: that would leak whether an inaccessible ID exists.
    patient = filters.UUIDFilter(field_name="patient_id")

    class Meta:
        model = Encounter
        fields = ["patient", "status"]
