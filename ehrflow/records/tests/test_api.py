import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import DatabaseError
from django.test import override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase
from rest_framework.throttling import SimpleRateThrottle

from records.demo import create_workspace
from records.models import AuditEvent, CareAssignment, ClinicalNote, DemoWorkspace, Encounter, NoteAddendum, Observation, Patient, Role, StaffProfile
from records.scenarios import NOTES


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class EHRTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workspace = create_workspace()
        cls.other_workspace = create_workspace()
        cls.people = {p.persona: p for p in cls.workspace.staff.select_related('user')}
        cls.maya = cls.workspace.patients.get(scenario='maya')
        cls.jonah = cls.workspace.patients.get(scenario='jonah')
        cls.encounter = cls.maya.encounters.get()
        cls.foreign = cls.other_workspace.patients.get(scenario='maya')

    def setUp(self):
        cache.clear()

    def login(self, persona='registrar'):
        self.client.force_authenticate(self.people[persona].user)

    def post(self, path, data=None):
        return self.client.post(path, data or {}, format='json')

    def draft(self):
        self.login('clinician')
        response = self.post(f'/api/encounters/{self.encounter.pk}/notes/', {'template': 'follow_up'})
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def finalize(self, note):
        response = self.post(f"/api/notes/{note['id']}/finalize/", {'version': note['version']})
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_home_uses_only_local_assets_and_sets_security_headers(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'EHRFlow API')
        self.assertContains(response, '/static/records/app.js')
        self.assertContains(response, 'id="start-button"')
        self.assertNotContains(response, '<script src="http')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertIn("script-src 'self'", response['Content-Security-Policy'])

    def test_protected_endpoints_require_authentication(self):
        for path in ['/api/users/me/', '/api/patients', '/api/encounters', '/api/staff', '/api/audit-events']:
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.post('/api/users', {'username': 'self', 'role': 'clinician'}).status_code, 404)

    def test_superuser_has_no_implicit_chart_access(self):
        user = get_user_model().objects.create_superuser('maintenance', 'admin@example.invalid', 'Test-82921!')
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get('/api/patients').status_code, 403)
        self.assertEqual(self.client.get('/api/audit-events').status_code, 403)

    def test_patient_list_scope_by_role(self):
        for persona, count in [('registrar', 3), ('clinician', 1), ('nurse', 1), ('other_clinician', 1)]:
            self.login(persona)
            response = self.client.get('/api/patients')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], count)
        for persona in ['reviewer', 'access_admin']:
            self.login(persona)
            self.assertEqual(self.client.get('/api/patients').status_code, 403)

    def test_search_filter_and_pagination_do_not_expand_access(self):
        self.login('clinician')
        for query in ['search=Beta', 'scenario=jonah', 'search=Patient%20Beta&ordering=-name']:
            response = self.client.get('/api/patients?' + query)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 0)
        self.login()
        response = self.client.get('/api/patients?page_size=1&ordering=-name')
        self.assertEqual(response.data['count'], 3)
        self.assertEqual(len(response.data['results']), 1)
        self.assertIsNotNone(response.data['next'])

    def test_encounter_patient_filter_does_not_leak_id_existence(self):
        self.login('clinician')
        for patient_id in [self.foreign.pk, self.jonah.pk, uuid.uuid4()]:
            response = self.client.get(f'/api/encounters?patient={patient_id}')
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data['count'], 0)
        self.assertEqual(self.client.get('/api/encounters?patient=invalid').status_code, 400)

    def test_unrelated_and_cross_workspace_chart_denied_and_audited(self):
        self.login('other_clinician')
        for patient_id in [self.maya.pk, self.foreign.pk]:
            self.assertEqual(self.client.get(f'/api/patients/{patient_id}/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/encounters/{self.encounter.pk}/clinical/').status_code, 404)
        self.assertEqual(AuditEvent.objects.filter(workspace=self.workspace, outcome='denied').count(), 3)

    def test_registrar_creates_only_allowlisted_synthetic_patient(self):
        self.login()
        response = self.post('/api/patients', {'scenario': 'theo'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['name'], 'Patient Delta')
        self.assertEqual(self.post('/api/patients', {'scenario': 'theo'}).status_code, 409)
        for data in [{'scenario': 'real'}, {'scenario': 'theo', 'name': 'Real person'}, {'scenario': 'theo', 'workspace': str(self.other_workspace.pk)}]:
            self.assertEqual(self.post('/api/patients', data).status_code, 400)
        self.assertEqual(Patient.objects.filter(workspace=self.workspace).count(), 4)

    def test_clinical_roles_cannot_register_patients(self):
        for persona in ['nurse', 'clinician', 'reviewer', 'access_admin']:
            self.login(persona)
            self.assertEqual(self.post('/api/patients', {'scenario': 'theo'}).status_code, 403)

    def test_contact_updates_use_version_and_fixed_values(self):
        self.login()
        path = f'/api/patients/{self.maya.pk}/'
        response = self.client.patch(path, {'contact': 'alternate', 'version': 1}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['contact_email'], 'alpha+alternate@example.invalid')
        self.assertEqual(response.data['version'], 2)
        self.assertEqual(self.client.patch(path, {'contact': 'primary', 'version': 1}, format='json').status_code, 409)
        self.assertEqual(self.client.patch(path, {'contact_email': 'real@example.com', 'version': 2}, format='json').status_code, 400)

    def test_schedule_and_assign_enforce_workspace_and_roles(self):
        self.login()
        avery = self.workspace.patients.get(scenario='avery')
        response = self.post('/api/encounters', {'patient': str(avery.pk), 'reason': 'intake'})
        self.assertEqual(response.status_code, 201)
        eid = response.data['id']
        self.assertEqual(self.post('/api/encounters', {'patient': str(avery.pk), 'reason': 'intake'}).status_code, 409)
        self.assertEqual(self.post('/api/encounters', {'patient': str(self.foreign.pk), 'reason': 'intake'}).status_code, 404)
        for staff in [self.people['access_admin'], self.other_workspace.staff.get(persona='clinician')]:
            self.assertEqual(self.post('/api/care-assignments', {'encounter': eid, 'staff': staff.pk}).status_code, 404)
        response = self.post('/api/care-assignments', {'encounter': eid, 'staff': self.people['clinician'].pk})
        self.assertEqual(response.status_code, 201, response.data)
        self.login('clinician')
        self.assertEqual(self.client.get(f'/api/encounters/{eid}/clinical/').status_code, 200)

    def test_assignment_revocation_takes_effect_on_next_request(self):
        assignment = self.encounter.assignments.get(staff=self.people['clinician'])
        self.login()
        self.assertEqual(self.client.delete(f'/api/care-assignments/{assignment.pk}/').status_code, 200)
        self.login('clinician')
        self.assertEqual(self.client.get(f'/api/patients/{self.maya.pk}/').status_code, 404)
        self.assertEqual(self.post(f'/api/encounters/{self.encounter.pk}/notes/', {'template': 'follow_up'}).status_code, 404)

    def test_expired_or_future_assignments_do_not_grant_access(self):
        assignment = self.encounter.assignments.get(staff=self.people['clinician'])
        self.login('clinician')
        for fields in [{'ends_at': timezone.now() - timedelta(seconds=1)}, {'ends_at': None, 'starts_at': timezone.now() + timedelta(hours=1)}]:
            CareAssignment.objects.filter(pk=assignment.pk).update(**fields)
            self.assertEqual(self.client.get(f'/api/patients/{self.maya.pk}/').status_code, 404)

    def test_observations_are_assigned_and_server_authored(self):
        path = f'/api/encounters/{self.encounter.pk}/observations/'
        self.login('nurse')
        response = self.post(path, {'kind': 'pulse'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['value'], '72.00')
        observation = Observation.objects.get(pk=response.data['id'])
        self.assertEqual(observation.author, self.people['nurse'])
        for payload in [{'kind': 'pulse', 'value': '100'}, {'kind': 'pulse', 'author': self.people['clinician'].pk}, {'kind': 'unknown'}]:
            self.assertEqual(self.post(path, payload).status_code, 400)
        self.login('other_clinician')
        self.assertEqual(self.post(path, {'kind': 'pulse'}).status_code, 404)

    def test_registrar_admin_reviewer_cannot_read_clinical_content(self):
        self.draft()
        for persona in ['registrar', 'reviewer', 'access_admin']:
            self.login(persona)
            response = self.client.get(f'/api/encounters/{self.encounter.pk}/clinical/')
            self.assertEqual(response.status_code, 403)
            self.assertNotIn(NOTES['follow_up'], str(response.data))

    def test_nurse_only_receives_finalized_summary_without_note_body(self):
        note = self.draft()
        self.login('nurse')
        path = f'/api/encounters/{self.encounter.pk}/clinical/'
        self.assertEqual(self.client.get(path).data['notes'], [])
        self.login('clinician')
        self.finalize(note)
        self.login('nurse')
        response = self.client.get(path)
        self.assertEqual(len(response.data['notes']), 1)
        self.assertNotIn('body', response.data['notes'][0])
        self.assertNotIn('template', response.data['notes'][0])
        self.assertEqual(self.post(f"/api/notes/{note['id']}/finalize/", {'version': 2}).status_code, 403)

    def test_note_finalization_addenda_and_stale_edits(self):
        note = self.draft()
        path = f"/api/notes/{note['id']}/"
        response = self.client.patch(path, {'template': 'reviewed', 'version': 1}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.patch(path, {'template': 'wellness', 'version': 1}, format='json').status_code, 409)
        self.assertEqual(self.post(path + 'finalize/', {'version': 1}).status_code, 409)
        finalized = self.finalize(response.data)
        self.assertEqual(self.client.patch(path, {'template': 'wellness', 'version': finalized['version']}, format='json').status_code, 409)
        response = self.post(path + 'addenda/', {'template': 'clarification', 'version': finalized['version']})
        self.assertEqual(response.status_code, 201)
        stored = ClinicalNote.objects.get(pk=note['id'])
        self.assertEqual(stored.body, NOTES['reviewed'])
        self.assertEqual(stored.addenda.count(), 1)
        self.assertEqual(stored.version, 4)
        self.assertEqual(self.post(path + 'addenda/', {'template': 'clarification', 'version': 3}).status_code, 409)

    def test_other_author_cannot_edit_note_even_when_assigned(self):
        note = self.draft()
        CareAssignment.objects.create(encounter=self.encounter, staff=self.people['other_clinician'], starts_at=timezone.now())
        self.login('other_clinician')
        response = self.client.get(f'/api/encounters/{self.encounter.pk}/clinical/')
        self.assertEqual(response.data['notes'], [])
        self.assertEqual(self.client.patch(f"/api/notes/{note['id']}/", {'template': 'reviewed', 'version': 1}, format='json').status_code, 403)

    def test_note_payload_cannot_override_body_author_or_encounter(self):
        self.login('clinician')
        for key, value in [('body', 'Real clinical text'), ('author', self.people['nurse'].pk), ('encounter', str(self.jonah.encounters.get().pk))]:
            self.assertEqual(self.post(f'/api/encounters/{self.encounter.pk}/notes/', {'template': 'follow_up', key: value}).status_code, 400)

    def test_complete_visit_requires_finalized_notes_and_blocks_new_records(self):
        note = self.draft()
        path = f'/api/encounters/{self.encounter.pk}/complete/'
        self.assertEqual(self.post(path, {'version': 1}).status_code, 409)
        self.finalize(note)
        self.assertEqual(self.post(path, {'version': 1}).status_code, 200)
        self.assertEqual(self.post(f'/api/encounters/{self.encounter.pk}/notes/', {'template': 'follow_up'}).status_code, 409)
        self.assertEqual(self.post(f'/api/encounters/{self.encounter.pk}/observations/', {'kind': 'pulse'}).status_code, 409)

    def test_access_admin_provisions_role_changes_and_deactivation(self):
        self.login('access_admin')
        response = self.post('/api/staff', {'role': 'nurse'})
        self.assertEqual(response.status_code, 201)
        self.assertFalse(StaffProfile.objects.get(pk=response.data['id']).user.has_usable_password())
        self.assertEqual(self.post('/api/staff', {'role': 'access_admin'}).status_code, 400)
        target = self.people['clinician']
        token = Token.objects.create(user=target.user)
        response = self.client.patch(f'/api/staff/{target.pk}/', {'active': False}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Token.objects.filter(pk=token.pk).exists())
        self.assertFalse(target.assignments.filter(active=True).exists())
        unauth = APIClient()
        unauth.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        self.assertEqual(unauth.get('/api/patients').status_code, 401)
        self.assertEqual(self.client.get('/api/patients').status_code, 403)

    def test_staff_role_change_revokes_assignments_and_cannot_self_elevate(self):
        self.login('access_admin')
        target = self.people['nurse']
        response = self.client.patch(f'/api/staff/{target.pk}/', {'role': 'clinician'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(target.assignments.filter(active=True).exists())
        self.assertEqual(self.client.patch(f"/api/staff/{self.people['access_admin'].pk}/", {'active': False}, format='json').status_code, 403)
        self.login('registrar')
        self.assertEqual(self.client.patch(f'/api/staff/{target.pk}/', {'role': 'reviewer'}, format='json').status_code, 403)

    def test_audit_read_permissions_fields_and_workspace_scope(self):
        self.login('clinician')
        self.client.get(f'/api/encounters/{self.encounter.pk}/clinical/')
        self.assertEqual(self.client.get('/api/audit-events').status_code, 403)
        self.login('reviewer')
        response = self.client.get('/api/audit-events?outcome=denied')
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.data['count'], 0)
        for event in response.data['results']:
            self.assertNotIn('body', event)
            self.assertNotIn('workspace', event)
            self.assertEqual(event['outcome'], 'denied')
        self.assertEqual(self.post('/api/audit-events', {}).status_code, 405)
        self.assertEqual(self.client.delete('/api/audit-events').status_code, 405)

    def test_clinical_read_fails_closed_if_audit_unavailable(self):
        self.login('clinician')
        with patch('records.audit.AuditEvent.objects.create', side_effect=DatabaseError('unavailable')):
            response = self.client.get(f'/api/encounters/{self.encounter.pk}/clinical/')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('observations', response.data)

    def test_mutation_rolls_back_if_audit_write_fails(self):
        self.login('nurse')
        with patch('records.audit.AuditEvent.objects.create', side_effect=DatabaseError('unavailable')):
            response = self.post(f'/api/encounters/{self.encounter.pk}/observations/', {'kind': 'pulse'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(Observation.objects.count(), 0)
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.status, 'scheduled')

    def test_denied_write_is_audited_after_transaction_rollback(self):
        note = self.draft()
        self.assertEqual(self.post(f"/api/notes/{note['id']}/finalize/", {'version': 100}).status_code, 409)
        self.assertTrue(AuditEvent.objects.filter(workspace=self.workspace, outcome='denied', action='post.NoteFinalize').exists())
        self.assertEqual(ClinicalNote.objects.get(pk=note['id']).status, 'draft')

    def test_audit_does_not_store_search_text_or_payload(self):
        self.login()
        self.client.get('/api/patients?search=DO_NOT_RECORD_THIS')
        self.post('/api/patients', {'scenario': 'invalid', 'password': 'DO_NOT_RECORD_THIS'})
        events = list(AuditEvent.objects.filter(workspace=self.workspace).values())
        self.assertNotIn('DO_NOT_RECORD_THIS', str(events))

    def test_workspace_expiration_revokes_access(self):
        self.login('clinician')
        DemoWorkspace.objects.filter(pk=self.workspace.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get('/api/patients').status_code, 401)

    def test_api_token_login_expiry_and_revocation(self):
        user = self.people['clinician'].user
        user.set_password('Local-Test-8291!')
        user.save()
        self.assertEqual(self.post('/api/token/login/', {'username': user.username, 'password': 'bad'}).status_code, 401)
        self.assertEqual(self.post('/api/token/login/', {}).status_code, 400)
        response = self.post('/api/token/login/', {'username': user.username, 'password': 'Local-Test-8291!'})
        self.assertEqual(response.status_code, 201, response.data)
        key = response.data['auth_token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {key}')
        self.assertEqual(self.client.get('/api/patients').status_code, 200)
        Token.objects.filter(key=key).update(created=timezone.now() - timedelta(minutes=31))
        self.assertEqual(self.client.get('/api/patients').status_code, 401)
        self.client.credentials()
        response = self.post('/api/token/login/', {'username': user.username, 'password': 'Local-Test-8291!'})
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {response.data['auth_token']}")
        self.assertEqual(self.post('/api/token/logout/').status_code, 200)
        self.assertEqual(self.client.get('/api/patients').status_code, 401)

    def test_login_attempt_limits_ignore_spoofed_forwarded_ips(self):
        with patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'login': '2/min'}):
            for n in [1, 2]:
                response = self.client.post('/api/token/login/', {'username': 'nobody', 'password': 'wrong'}, format='json', HTTP_X_FORWARDED_FOR=f'192.0.2.{n}')
                self.assertEqual(response.status_code, 401)
            self.assertEqual(self.post('/api/token/login/', {'username': 'nobody', 'password': 'wrong'}).status_code, 429)

    def test_login_rejects_malformed_payloads_and_excessive_password_length(self):
        self.assertEqual(self.client.post('/api/token/login/', [], format='json').status_code, 400)
        self.assertEqual(self.post('/api/token/login/', {'username': 'nobody', 'password': 'x' * 129}).status_code, 400)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class BrowserJourneyTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.browser = APIClient(enforce_csrf_checks=True)

    def send(self, path, data=None, method='post'):
        cookie = self.browser.cookies.get('ehrflow_csrf')
        return getattr(self.browser, method)(path, data or {}, format='json', HTTP_X_CSRFTOKEN=cookie.value if cookie else '')

    def start(self):
        self.browser.get('/')
        response = self.send('/api/demo/start/')
        self.assertEqual(response.status_code, 201, getattr(response, 'data', response.content))
        return response.data

    def switch(self, persona):
        response = self.send('/api/demo/switch/', {'persona': persona})
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_demo_start_requires_csrf_even_for_anonymous_user(self):
        self.assertEqual(self.browser.post('/api/demo/start/', {}, format='json').status_code, 403)
        self.assertEqual(DemoWorkspace.objects.count(), 0)

    def test_complete_browser_workflow_uses_sessions_and_scoped_api(self):
        session = self.start()
        self.assertFalse(get_user_model().objects.filter(is_staff=True).exists())
        patients = self.browser.get('/api/patients').data['results']
        maya = next(p for p in patients if p['scenario'] == 'maya')
        encounter = self.browser.get(f"/api/encounters?patient={maya['id']}").data['results'][0]
        clinical_path = f"/api/encounters/{encounter['id']}/clinical/"
        self.assertEqual(self.browser.get(clinical_path).status_code, 403)
        self.switch('nurse')
        self.assertEqual(self.send(f"/api/encounters/{encounter['id']}/observations/", {'kind': 'pulse'}).status_code, 201)
        self.switch('clinician')
        note = self.send(f"/api/encounters/{encounter['id']}/notes/", {'template': 'follow_up'})
        self.assertEqual(note.status_code, 201)
        self.assertEqual(self.send(f"/api/notes/{note.data['id']}/finalize/", {'version': 1}).status_code, 200)
        self.switch('other_clinician')
        self.assertEqual(self.browser.get(f"/api/patients/{maya['id']}/").status_code, 404)
        self.switch('reviewer')
        events = self.browser.get('/api/audit-events?outcome=denied')
        self.assertEqual(events.status_code, 200)
        self.assertGreaterEqual(events.data['count'], 2)
        self.assertEqual(self.browser.get(clinical_path).status_code, 403)
        self.assertEqual(self.send('/api/demo/logout/').status_code, 200)
        self.assertEqual(self.browser.get('/api/users/me/').status_code, 401)

    def test_two_reviewers_are_isolated_and_reset_expires_only_own_workspace(self):
        first = self.start()
        first_patient = self.browser.get('/api/patients').data['results'][0]
        browser1 = self.browser
        self.browser = APIClient(enforce_csrf_checks=True)
        second = self.start()
        self.assertNotEqual(first['workspace'], second['workspace'])
        self.assertEqual(self.browser.get(f"/api/patients/{first_patient['id']}/").status_code, 404)
        reset = self.send('/api/demo/reset/')
        self.assertEqual(reset.status_code, 201)
        self.assertNotEqual(reset.data['workspace'], second['workspace'])
        self.assertEqual(browser1.get(f"/api/patients/{first_patient['id']}/").status_code, 200)
        old = DemoWorkspace.objects.get(pk=second['workspace'])
        self.assertLess(old.expires_at, timezone.now())

    def test_role_switch_rejects_forged_workspace_and_unknown_persona(self):
        self.start()
        self.assertEqual(self.send('/api/demo/switch/', {'persona': 'superuser'}).status_code, 404)
        self.assertEqual(self.send('/api/demo/switch/', {'persona': 'clinician', 'workspace': str(uuid.uuid4())}).status_code, 400)

    def test_token_alone_cannot_switch_demo_personas(self):
        session = self.start()
        profile = StaffProfile.objects.get(pk=session['user']['id'])
        token = Token.objects.create(user=profile.user)
        client = APIClient(enforce_csrf_checks=True)
        client.get('/')
        client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        response = client.post('/api/demo/switch/', {'persona': 'clinician'}, format='json', HTTP_X_CSRFTOKEN=client.cookies['ehrflow_csrf'].value)
        self.assertEqual(response.status_code, 403)

    def test_session_mutations_require_csrf(self):
        self.start()
        self.assertEqual(self.browser.post('/api/patients', {'scenario': 'theo'}, format='json').status_code, 403)

    def test_disabled_persona_cannot_be_selected(self):
        session = self.start()
        self.switch('access_admin')
        clinician = next(p for p in session['personas'] if p['persona'] == 'clinician')
        self.assertEqual(self.send(f"/api/staff/{clinician['id']}/", {'active': False}, 'patch').status_code, 200)
        self.assertEqual(self.send('/api/demo/switch/', {'persona': 'clinician'}).status_code, 404)
