from django.urls import path, re_path
from records import demo, views

urlpatterns = [
    path("", views.index, name="home"),
    path("api/demo/start/", demo.DemoStart.as_view()),
    path("api/demo/switch/", demo.DemoSwitch.as_view()),
    path("api/demo/reset/", demo.DemoReset.as_view()),
    path("api/demo/logout/", demo.DemoLogout.as_view()),
    re_path(r"^api/users/me/?$", views.Me.as_view()),
    re_path(r"^api/token/login/?$", views.TokenLogin.as_view()),
    re_path(r"^api/token/logout/?$", views.TokenLogout.as_view()),
    re_path(r"^api/patients/?$", views.PatientList.as_view()),
    path("api/patients/<uuid:pk>/", views.PatientDetail.as_view()),
    re_path(r"^api/encounters/?$", views.EncounterList.as_view()),
    path("api/encounters/<uuid:pk>/", views.EncounterDetail.as_view()),
    path("api/encounters/<uuid:pk>/clinical/", views.ClinicalRead.as_view()),
    path("api/encounters/<uuid:pk>/observations/", views.ObservationList.as_view()),
    path("api/encounters/<uuid:pk>/notes/", views.NoteList.as_view()),
    path("api/encounters/<uuid:pk>/complete/", views.EncounterComplete.as_view()),
    re_path(r"^api/care-assignments/?$", views.AssignmentList.as_view()),
    path("api/care-assignments/<uuid:pk>/", views.AssignmentDetail.as_view()),
    path("api/notes/<uuid:pk>/", views.NoteDetail.as_view()),
    path("api/notes/<uuid:pk>/finalize/", views.NoteFinalize.as_view()),
    path("api/notes/<uuid:pk>/addenda/", views.AddendumList.as_view()),
    re_path(r"^api/staff/?$", views.StaffList.as_view()),
    path("api/staff/<int:pk>/", views.StaffDetail.as_view()),
    re_path(r"^api/audit-events/?$", views.AuditList.as_view()),
]
