'use strict';
(function () {
  const $ = (selector) => document.querySelector(selector);
  const content = $('#content');
  const dialog = $('#form-dialog');
  const state = { user: null, personas: [], route: 'overview', page: 1, search: '', ordering: 'name', outcome: '', patients: [], encounters: [], staff: [], currentPatient: null, currentEncounter: null, clinical: null, probe: null, request: 0 };
  const roles = { registrar: 'Registrar', nurse: 'Nurse', clinician: 'Clinician', reviewer: 'Privacy reviewer', access_admin: 'Access administrator' };
  const roleNotes = {
    registrar: ['Administrative access', 'Register patients, schedule visits, and assign care. Clinical notes and observations are outside your role.'],
    nurse: ['Assigned care only', 'Record observations and see finalized summary metadata for assigned encounters. Clinician note content and drafts remain restricted.'],
    clinician: ['Care relationship required', 'Open assigned charts, author notes, and finalize your own documentation. Unrelated charts remain inaccessible.'],
    reviewer: ['Oversight without clinical content', 'Review allowed and denied access events. Audit metadata does not grant access to patient charts.'],
    access_admin: ['Administration is not clinical access', 'Manage staff roles and deactivate accounts. No patient or clinical access is granted by this role.']
  };
  const pages = {
    'patient-detail': ['Patient record', 'Demographics and visits within your permitted scope.'],
    'encounter-detail': ['Encounter workspace', 'Document care with clear ownership and a complete history.'],
    overview: ['Your clinical workspace', 'A clear view of care, within your role.'],
    patients: ['Patient directory', 'Find the patients your role and care relationship allow you to see.'],
    encounters: ['Encounter workspace', 'Move each visit from scheduled care to complete documentation.'],
    audit: ['Access ledger', 'A traceable record of what happened, who acted, and the outcome.'],
    staff: ['Staff access', 'Give each person the access their work requires.'],
    policy: ['Privacy by design', 'The decisions behind the workflow—and the boundaries of this demo.']
  };
  function esc(value) { return String(value == null ? '' : value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
  function icon(name) { return '<svg aria-hidden="true"><use href="#i-' + name + '"/></svg>'; }
  function initials(name) { return name.replace(/^Dr\. /, '').split(' ').slice(0, 2).map(s => s[0]).join(''); }
  function date(value) { return new Date(value).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }); }
  function badge(status) { const names = { scheduled: 'Scheduled', in_progress: 'In progress', completed: 'Completed', finalized: 'Finalized', draft: 'Draft' }; return '<span class="chip ' + (status === 'completed' || status === 'finalized' ? 'green' : status === 'draft' ? 'amber' : 'blue') + '">' + esc(names[status] || status) + '</span>'; }
  function empty(title, text) { return '<div class="empty">' + icon('file') + '<h3>' + esc(title) + '</h3><p>' + esc(text) + '</p></div>'; }
  function csrf() { const cookie = document.cookie.split('; ').find(c => c.indexOf('ehrflow_csrf=') === 0); return cookie ? decodeURIComponent(cookie.split('=').slice(1).join('=')) : ''; }
  function message(data) { if (typeof data === 'string') return data; if (Array.isArray(data)) return data.map(message).join(' '); if (data && typeof data === 'object') return Object.keys(data).map(k => (k === 'detail' || k === 'non_field_errors' ? '' : k + ': ') + message(data[k])).join(' '); return 'Request could not be completed.'; }
  async function api(path, method, data) {
    method = method || 'GET';
    const opts = { method, credentials: 'same-origin', headers: { Accept: 'application/json' }, cache: 'no-store' };
    if (method !== 'GET') { opts.headers['Content-Type'] = 'application/json'; opts.headers['X-CSRFToken'] = csrf(); opts.body = JSON.stringify(data || {}); }
    const response = await fetch(path, opts);
    let body;
    try { body = await response.json(); } catch (_) { body = { detail: 'The server could not complete the request.' }; }
    if (!response.ok) { const error = new Error(message(body)); error.status = response.status; throw error; }
    return body;
  }
  let noticeTimer;
  function notify(text, error) { const box = $('#notification'); box.textContent = text; box.className = error ? 'error' : ''; box.hidden = false; clearTimeout(noticeTimer); noticeTimer = setTimeout(() => { box.hidden = true; }, 6500); }
  function showWelcome() { state.user = null; state.request++; $('#welcome').hidden = false; $('#workspace').hidden = true; $('#reset-button').hidden = true; $('#logout-button').hidden = true; }
  function acceptSession(session) {
    state.user = session.user; state.personas = session.personas; state.currentPatient = null; state.currentEncounter = null; state.clinical = null;
    $('#welcome').hidden = true; $('#workspace').hidden = false; $('#reset-button').hidden = false; $('#logout-button').hidden = false;
    $('#logout-button').textContent = initials(state.user.display_name);
    $('#persona').innerHTML = state.personas.map(p => '<option value="' + esc(p.persona) + '">' + esc(p.display_name + ' · ' + (roles[p.role] || p.role)) + '</option>').join('');
    $('#persona').value = state.user.persona;
    const note = roleNotes[state.user.role] || ['No access', 'This account has no assigned role.'];
    $('#role-banner').innerHTML = icon('shield') + '<p><strong>' + esc(note[0]) + '.</strong> ' + esc(note[1]) + '</p>';
  }
  async function switchPersona(persona) {
    const session = await api('/api/demo/switch/', 'POST', { persona });
    acceptSession(session); state.page = 1; state.search = ''; state.ordering = 'name';
    if (state.user.role === 'reviewer') state.route = 'audit'; else if (state.user.role === 'access_admin') state.route = 'staff'; else state.route = 'overview';
    await render(); notify('Now exploring as ' + state.user.display_name + '.');
  }
  function pager(data) { return '<div class="pagination"><span>' + data.count + ' result' + (data.count === 1 ? '' : 's') + ' · Page ' + state.page + '</span><div class="buttons"><button class="secondary small" data-page="' + (state.page - 1) + '" ' + (!data.previous ? 'disabled' : '') + '>Previous</button><button class="secondary small" data-page="' + (state.page + 1) + '" ' + (!data.next ? 'disabled' : '') + '>Next</button></div></div>'; }
  function personCell(name, subtitle) { return '<div class="person-cell"><span class="avatar mint">' + esc(initials(name)) + '</span><div><strong>' + esc(name) + '</strong><small>' + esc(subtitle) + '</small></div></div>'; }
  function journey() {
    const steps = [
      ['Registration', 'Create Patient Delta from a fictional scenario.', 'registrar'],
      ['Care assignment', 'Schedule a visit and assign a nurse and clinician.', 'registrar'],
      ['Intake', 'Record a predefined observation for an assigned visit.', 'nurse'],
      ['Clinical documentation', 'Draft, finalize, and add a correction.', 'clinician'],
      ['Try an unrelated chart', 'Observe an actual API denial as another clinician.', 'other_clinician'],
      ['Review the evidence', 'Inspect the access ledger as a privacy reviewer.', 'reviewer']
    ];
    return '<div class="card"><div class="card-header"><div><span class="eyebrow">A FIVE-MINUTE WALKTHROUGH</span><h2>Follow the care journey</h2></div>' + icon('arrow') + '</div><ol class="journey">' + steps.map((s, i) => '<li><span class="step-number">' + (i + 1) + '</span><div><strong>' + s[0] + '</strong><p>' + s[1] + '</p><button class="link-button" data-switch="' + s[2] + '">Explore this role →</button></div></li>').join('') + '</ol><div class="panel-note">Your demo is isolated. Switching roles never changes another reviewer’s workspace.</div></div>';
  }
  function patientsTable(data, toolbar) {
    return '<div class="card"><div class="card-header"><div><h2>' + (state.user.role === 'registrar' ? 'Patient directory' : 'Your assigned patients') + '</h2><p>Only records within your permitted scope</p></div>' + (state.user.role === 'registrar' ? '<button class="primary" data-action="register">' + icon('plus') + 'Register patient</button>' : '<span class="chip green">CARE-TEAM ACCESS</span>') + '</div>' + (toolbar ? '<form class="toolbar" id="patient-search"><div class="search-box">' + icon('search') + '<input aria-label="Search synthetic patients" name="search" value="' + esc(state.search) + '" placeholder="Search name or record number"></div><select name="ordering" aria-label="Sort patients"><option value="name" ' + (state.ordering === 'name' ? 'selected' : '') + '>Name A–Z</option><option value="-name" ' + (state.ordering === '-name' ? 'selected' : '') + '>Name Z–A</option></select><button class="secondary" type="submit">Search</button></form>' : '') + (data.results.length ? '<div class="table-wrap"><table><thead><tr><th>Patient</th><th>Record</th><th>Action</th></tr></thead><tbody>' + data.results.map(p => '<tr><td>' + personCell(p.name, 'Synthetic patient') + '</td><td><span class="audit-action">' + esc(p.record_number) + '</span></td><td><button class="link-button" data-patient="' + p.id + '">Open record →</button></td></tr>').join('') + '</tbody></table></div>' : empty('No patients found', 'Try another search or ask the registrar to assign care.')) + pager(data) + '</div>';
  }
  function encounterTable(data) {
    return '<div class="card"><div class="card-header"><div><h2>Visits in your scope</h2><p>Assignment is checked on every request</p></div>' + (state.user.role === 'registrar' ? '<button class="primary" data-action="schedule">' + icon('plus') + 'Schedule visit</button>' : '') + '</div>' + (data.results.length ? '<div class="table-wrap"><table><thead><tr><th>Patient</th><th>Visit</th><th>Status</th><th></th></tr></thead><tbody>' + data.results.map(e => '<tr><td>' + personCell(e.patient_name, e.record_number) + '</td><td>' + esc(e.reason_label) + '<br><small class="muted">' + esc(date(e.scheduled_at)) + '</small></td><td>' + badge(e.status) + '</td><td><button class="link-button" data-encounter="' + e.id + '">Open visit →</button></td></tr>').join('') + '</tbody></table></div>' : empty('No encounters yet', 'Schedule a visit as the registrar, then assign a care team.')) + pager(data) + '</div>';
  }
  function denialCard() {
    if (state.user.persona !== 'other_clinician') return '';
    return '<div class="card"><div class="card-body"><span class="eyebrow">CHECK THE BOUNDARY</span><h2>Can you open an unrelated chart?</h2><p class="muted">This clinician is assigned to Patient Beta. Try the Patient Alpha record you saw as registrar.</p><button class="secondary" data-action="probe">' + icon('lock') + 'Test unrelated chart access</button><div id="probe-result" role="status"></div></div></div>';
  }
  async function render() {
    if (!state.user) return;
    const serial = ++state.request;
    const page = pages[state.route] || pages.overview;
    $('#page-title').textContent = page[0]; $('#page-description').textContent = page[1];
    document.querySelectorAll('[data-route]').forEach(b => { b.classList.toggle('active', b.dataset.route === state.route); if (b.dataset.route === state.route) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current'); });
    content.setAttribute('aria-busy', 'true'); content.innerHTML = '<div class="loading">Loading your workspace…</div>';
    try {
      let html = '';
      if (state.route === 'policy') html = policyView();
      else if (state.route === 'audit') {
        const data = await api('/api/audit-events?page=' + state.page + '&page_size=10' + (state.outcome ? '&outcome=' + state.outcome : ''));
        html = auditView(data);
      } else if (state.route === 'staff') {
        state.staff = await api('/api/staff'); html = staffView();
      } else if (state.route === 'patient-detail') {
        html = await patientView(state.currentPatient);
      } else if (state.route === 'encounter-detail') {
        html = await encounterView(typeof state.currentEncounter === 'object' ? state.currentEncounter.id : state.currentEncounter);
      } else if (state.route === 'encounters') {
        const data = await api('/api/encounters?page=' + state.page); state.encounters = data.results; html = encounterTable(data);
      } else if (state.user.role === 'reviewer' || state.user.role === 'access_admin') {
        html = '<div class="content-grid"><div class="card"><div class="card-body"><span class="eyebrow">YOUR ROLE</span><h2>' + roles[state.user.role] + '</h2><p class="muted">' + esc(roleNotes[state.user.role][1]) + '</p><button class="primary" data-route="' + (state.user.role === 'reviewer' ? 'audit' : 'staff') + '">Open your workspace ' + icon('arrow') + '</button></div></div>' + journey() + '</div>';
      } else {
        const data = await api('/api/patients?page=' + state.page + '&page_size=5&search=' + encodeURIComponent(state.search) + '&ordering=' + encodeURIComponent(state.ordering));
        state.patients = data.results;
        const maya = data.results.find(p => p.scenario === 'maya'); if (maya) state.probe = maya.id;
        if (state.route === 'patients') html = patientsTable(data, true);
        else {
          const encounters = await api('/api/encounters?page_size=50'); state.encounters = encounters.results;
          html = '<div class="stats"><div class="stat"><div><span class="stat-label">Patients in your scope</span><strong>' + data.count + '</strong><small>Access checked by the server</small></div><span class="stat-icon">' + icon('users') + '</span></div><div class="stat"><div><span class="stat-label">Visible encounters</span><strong>' + encounters.count + '</strong><small>Within your care responsibilities</small></div><span class="stat-icon">' + icon('file') + '</span></div><div class="stat"><div><span class="stat-label">Data environment</span><strong>100%</strong><small>Synthetic · no real patient records</small></div><span class="stat-icon">' + icon('shield') + '</span></div></div><div class="content-grid"><div>' + patientsTable(data, true) + denialCard() + '</div>' + journey() + '</div>';
        }
      }
      if (serial === state.request) content.innerHTML = html;
    } catch (error) {
      if (serial !== state.request) return;
      if (error.status === 401) { showWelcome(); notify('Your session expired. Start a fresh demo.', true); }
      else content.innerHTML = '<div class="card">' + empty(error.status === 403 ? 'This view belongs to another role' : 'Unable to load this view', error.message) + '<div class="panel-note">The API enforces this boundary. Use the persona selector to explore the corresponding role.</div></div>';
    } finally { if (serial === state.request) content.setAttribute('aria-busy', 'false'); }
  }
  async function patientView(id) {
    const p = await api('/api/patients/' + id + '/'); state.currentPatient = p.id;
    const visits = await api('/api/encounters?patient=' + id + '&page=' + state.page); state.encounters = visits.results;
    return '<button class="link-button" data-route="patients">← Patient directory</button><div class="content-grid"><div><div class="card"><div class="detail-head"><span class="avatar mint">' + esc(initials(p.name)) + '</span><div><h2>' + esc(p.name) + '</h2><p>' + esc(p.record_number) + ' · Fictional patient</p></div><span class="chip">SYNTHETIC</span></div><dl class="data-grid"><div><dt>Date of birth</dt><dd>' + esc(p.date_of_birth) + '</dd></div><div><dt>Contact</dt><dd>' + esc(p.contact_email) + '</dd></div><div><dt>Classification</dt><dd>Patient administration</dd></div><div><dt>Record version</dt><dd>' + p.version + '</dd></div></dl>' + (state.user.role === 'registrar' ? '<div class="panel-note"><button class="link-button" data-contact="' + p.id + '" data-version="' + p.version + '">Use alternate synthetic contact →</button></div>' : '') + '</div>' + encounterTable(visits) + '</div><div>' + (state.user.role === 'registrar' ? '<div class="card"><div class="card-body"><span class="eyebrow">ADMINISTRATIVE VIEW</span><h2>Enough information for the task</h2><p class="muted">You can manage demographics and schedule care. Clinical documentation is not included in this role’s response.</p><button class="primary" data-action="schedule">Schedule a visit</button></div></div>' : journey()) + '</div></div>';
  }
  async function encounterView(id) {
    const e = await api('/api/encounters/' + id + '/'); state.currentEncounter = e;
    const registrar = state.user.role === 'registrar';
    let clinicalHtml = '';
    if (registrar) {
      state.staff = await api('/api/staff');
      clinicalHtml = '<div class="restriction"><strong>Clinical content is restricted</strong>Registration staff can schedule and assign care. Observations and clinical notes require a care-team role and an active assignment.</div>';
    } else {
      const c = await api('/api/encounters/' + id + '/clinical/'); state.clinical = c;
      clinicalHtml = '<div class="section-heading"><h3>Observations</h3>' + (e.status !== 'completed' ? '<button class="secondary small" data-action="observe">' + icon('plus') + 'Record observation</button>' : '') + '</div>' + (c.observations.length ? c.observations.map(o => '<div class="observation"><small>' + esc(o.kind.replace(/_/g, ' ')) + '</small><strong>' + esc(o.value) + ' <span>' + esc(o.unit) + '</span></strong><small>' + esc(o.author_name) + '</small></div>').join('') : '<p class="muted">No observations recorded for this visit.</p>') + '<div class="section-heading" style="margin-top:25px"><h3>' + (state.user.role === 'nurse' ? 'Finalized summary' : 'Clinical documentation') + '</h3>' + (state.user.role === 'clinician' && e.status !== 'completed' ? '<button class="primary small" data-action="draft">' + icon('plus') + 'Draft note</button>' : '') + '</div>' + (c.notes.length ? c.notes.map(noteView).join('') : '<p class="muted">' + (state.user.role === 'nurse' ? 'No finalized summary yet. Draft notes are restricted to their author.' : 'No visible notes yet. Start a draft from a synthetic template.') + '</p>');
    }
    return '<button class="link-button" data-route="encounters">← All encounters</button><div class="content-grid"><div class="card"><div class="detail-head"><span class="avatar mint">' + esc(initials(e.patient_name)) + '</span><div><h2>' + esc(e.patient_name) + '</h2><p>' + esc(e.reason_label) + ' · ' + esc(e.record_number) + '</p></div>' + badge(e.status) + '</div><div class="card-body">' + clinicalHtml + '</div></div><div><div class="card"><div class="card-header"><div><span class="eyebrow">CARE RELATIONSHIP</span><h2>Assigned team</h2></div>' + icon('users') + '</div><div class="card-body" style="padding-top:0">' + (e.assignments.filter(a => a.active).map(a => '<div class="assignment-row"><span class="avatar">' + esc(initials(a.name)) + '</span><div><strong>' + esc(a.name) + '</strong><small>' + esc(roles[a.role]) + '</small></div>' + (registrar ? '<button class="text-button" data-revoke="' + a.id + '">Revoke</button>' : '') + '</div>').join('') || '<p class="muted">No active care assignment.</p>') + (registrar && e.status !== 'completed' ? '<div class="action-row"><button class="primary" data-action="assign">Assign care team</button></div>' : '') + '</div><div class="panel-note">Access is tied to the encounter and the active care assignment. Revocation takes effect on the next request.</div></div><div class="card"><div class="card-body"><h3>Visit details</h3><p class="muted">' + esc(date(e.scheduled_at)) + '</p><p class="muted">Version ' + e.version + ' · Synthetic encounter</p>' + (state.user.role === 'clinician' && e.status !== 'completed' ? '<button class="secondary" data-action="complete">Complete visit</button>' : '') + '</div></div></div></div>';
  }
  function noteView(n) {
    if (state.user.role === 'nurse') return '<div class="note"><div class="note-header"><strong>' + esc(n.author_name) + '</strong>' + badge(n.status) + '</div><p class="muted">' + esc(n.summary) + '</p></div>';
    const own = n.author === state.user.id;
    return '<article class="note"><div class="note-header"><div><strong>' + esc(n.author_name) + '</strong><br><small>Version ' + n.version + ' · ' + esc(date(n.finalized_at || n.created_at)) + '</small></div>' + badge(n.status) + '</div><p class="note-body">' + esc(n.body) + '</p>' + (n.addenda || []).map(a => '<div class="addendum"><strong>Addendum · ' + esc(a.author_name) + '</strong><p>' + esc(a.body) + '</p><small>' + esc(date(a.created_at)) + '</small></div>').join('') + (own ? '<div class="action-row">' + (n.status === 'draft' ? '<button class="secondary small" data-edit-note="' + n.id + '">Revise draft</button><button class="primary small" data-finalize="' + n.id + '">Finalize note</button>' : '<button class="secondary small" data-addendum="' + n.id + '">Add correction</button>') + '</div>' : '') + '</article>';
  }
  function auditView(data) {
    return '<div class="card"><div class="card-header"><div><h2>Recorded activity</h2><p>Metadata only. No note bodies, passwords, or tokens.</p></div><span class="chip">APPEND-ONLY API</span></div><div class="toolbar"><select id="audit-filter" aria-label="Filter audit outcome"><option value="">All outcomes</option><option value="allowed" ' + (state.outcome === 'allowed' ? 'selected' : '') + '>Allowed</option><option value="denied" ' + (state.outcome === 'denied' ? 'selected' : '') + '>Denied</option></select><button class="secondary small" data-action="refresh">Refresh</button></div>' + (data.results.length ? '<div class="table-wrap"><table><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Outcome</th></tr></thead><tbody>' + data.results.map(e => '<tr><td><small>' + esc(date(e.created_at)) + '</small></td><td><strong>' + esc(e.actor_name) + '</strong><br><small class="muted">' + esc(roles[e.role]) + '</small></td><td><span class="audit-action">' + esc(e.action) + '</span><br><small class="muted">' + esc(e.resource_type) + (e.resource_id ? ' · ' + esc(e.resource_id.slice(0, 8)) : '') + '</small></td><td><span class="outcome ' + (e.outcome === 'denied' ? 'denied' : '') + '">' + esc(e.outcome) + '</span></td></tr>').join('') + '</tbody></table></div>' : empty('No matching events', 'Try another outcome filter.')) + pager(data) + '<div class="panel-note">Events cannot be edited through this API. The SQLite database is not tamper-proof against its administrator.</div></div>';
  }
  function staffView() {
    const admin = state.user.role === 'access_admin';
    return '<div class="card"><div class="card-header"><div><h2>Staff directory</h2><p>' + (admin ? 'Role changes revoke existing assignments. Disabled accounts lose API access.' : 'Active clinical staff available for care assignment.') + '</p></div>' + (admin ? '<button class="primary" data-action="provision">' + icon('plus') + 'Provision trainee</button>' : '') + '</div><div class="table-wrap"><table><thead><tr><th>Staff member</th><th>Role</th><th>Status</th><th></th></tr></thead><tbody>' + state.staff.map(s => '<tr><td>' + personCell(s.display_name, 'Synthetic staff account') + '</td><td>' + esc(roles[s.role]) + '</td><td><span class="chip ' + (s.active ? 'green' : 'red') + '">' + (s.active ? 'Active' : 'Inactive') + '</span></td><td>' + (admin && s.role !== 'access_admin' ? '<button class="link-button" data-edit-staff="' + s.id + '">Manage →</button>' : '<span class="muted">' + (admin ? 'Protected' : 'Assignable') + '</span>') + '</td></tr>').join('') + '</tbody></table></div></div>';
  }
  function policyView() {
    return '<div class="policy-grid"><section class="card"><div class="card-body"><span class="eyebrow">01 · IDENTITY & AUTHORIZATION</span><h2>Signing in is the beginning</h2><p>The backend checks role, care assignment, workspace, record state, and authorship. An administrator can manage staff without receiving clinical access.</p><p>All lists, detail routes, searches, and mutations apply these rules. Hiding a button alone would not enforce access.</p></div></section><section class="card"><div class="card-body"><span class="eyebrow">02 · MINIMUM NECESSARY</span><h2>Access follows the task</h2><p>Registrars receive administrative fields. Nurses see observations and finalized summary metadata. Clinicians receive documentation for assigned visits.</p><p>HIPAA’s minimum necessary standard has exceptions, including disclosures to or requests by a provider for treatment. Our assignment rules are an explicit demonstration policy.</p><a href="https://www.hhs.gov/hipaa/for-professionals/privacy/guidance/minimum-necessary-requirement/index.html" target="_blank" rel="noopener noreferrer">Read the HHS guidance ↗</a></div></section><section class="card"><div class="card-body"><span class="eyebrow">03 · DATA CLASSIFICATION</span><h2>Context makes data sensitive</h2><p>Patient demographics linked to a visit, clinical content, and patient-linked audit metadata all need deliberate access policies. Replacing a name with an ID does not automatically de-identify a record.</p><p>Every person and record here is invented. This demo does not transform real records into de-identified data.</p></div></section><section class="card"><div class="card-body"><span class="eyebrow">04 · INTEGRITY & LIMITS</span><h2>A correction should leave a history</h2><p>Finalized notes cannot be overwritten through the API. Addenda retain author and time. Version checks reject stale writes, and transactions keep audit events with successful changes.</p><p>This is a portfolio prototype, not HIPAA certification or a clinical service. No decision support, prescriptions, real patient data, or patient-rights workflow is provided.</p></div></section></div>';
  }
  function field(name, label, options, help) { return '<div class="form-field"><label for="field-' + name + '">' + esc(label) + '</label><select id="field-' + name + '" name="' + name + '" required>' + options.map(o => '<option value="' + esc(o[0]) + '">' + esc(o[1]) + '</option>').join('') + '</select>' + (help ? '<small>' + esc(help) + '</small>' : '') + '</div>'; }
  function openForm(title, html, submitLabel, callback) {
    $('#dialog-title').textContent = title;
    $('#dialog-body').innerHTML = '<form id="action-form">' + html + '<p class="form-error" id="form-error" role="alert" hidden></p><div class="form-actions"><button class="secondary" type="button" id="cancel-form">Cancel</button><button class="primary" type="submit">' + esc(submitLabel) + '</button></div></form>';
    $('#cancel-form').onclick = () => dialog.close();
    $('#action-form').onsubmit = async (event) => {
      event.preventDefault(); const button = event.target.querySelector('[type=submit]'); button.disabled = true; $('#form-error').hidden = true;
      try { await callback(Object.fromEntries(new FormData(event.target).entries())); dialog.close(); await render(); }
      catch (error) { $('#form-error').textContent = error.message; $('#form-error').hidden = false; }
      finally { button.disabled = false; }
    };
    dialog.showModal();
  }
  async function action(name) {
    const e = state.currentEncounter;
    if (name === 'register') openForm('Register a synthetic patient', field('scenario', 'Patient scenario', [['theo', 'Patient Delta · new patient'], ['avery', 'Patient Gamma'], ['maya', 'Patient Alpha'], ['jonah', 'Patient Beta']], 'Names and details come from fictional fixtures. No real patient entry.'), 'Register patient', async d => { const p = await api('/api/patients', 'POST', d); state.currentPatient = p.id; state.route = 'patient-detail'; notify('Synthetic patient registered.'); });
    if (name === 'schedule') { const patients = await api('/api/patients?page_size=50'); openForm('Schedule a visit', field('patient', 'Synthetic patient', patients.results.map(p => [p.id, p.name])) + field('reason', 'Visit scenario', [['follow_up', 'Routine follow-up'], ['wellness', 'Wellness visit'], ['intake', 'New patient intake']]), 'Schedule visit', async d => { const encounter = await api('/api/encounters', 'POST', d); state.currentEncounter = encounter.id; state.route = 'encounter-detail'; notify('Visit scheduled. Assign a care team next.'); }); }
    if (name === 'assign') { const staff = await api('/api/staff'); const eligible = staff.filter(s => !e.assignments.some(a => a.active && a.staff === s.id)); if (!eligible.length) return notify('All available clinical staff are already assigned.'); openForm('Assign a care-team member', field('staff', 'Active clinical staff', eligible.map(s => [s.id, s.display_name + ' · ' + roles[s.role]])), 'Assign care', async d => { await api('/api/care-assignments', 'POST', { encounter: e.id, staff: Number(d.staff) }); notify('Care assignment created.'); }); }
    if (name === 'observe') openForm('Record a synthetic observation', field('kind', 'Predefined sample', [['pulse', 'Pulse · 72 bpm'], ['temperature', 'Temperature · 36.7 °C'], ['oxygen_saturation', 'Oxygen saturation · 98%']], 'These fixed values demonstrate documentation, not clinical interpretation.'), 'Record observation', async d => { await api('/api/encounters/' + e.id + '/observations/', 'POST', d); notify('Observation recorded and audited.'); });
    if (name === 'draft') openForm('Draft a clinical note', field('template', 'Synthetic narrative', [['follow_up', 'Routine follow-up'], ['reviewed', 'Reviewed intake'], ['wellness', 'Wellness encounter']], 'The server supplies fictional text. Drafts remain visible only to their author.'), 'Create draft', async d => { await api('/api/encounters/' + e.id + '/notes/', 'POST', d); notify('Draft created. Review before finalizing.'); });
    if (name === 'complete') { await api('/api/encounters/' + e.id + '/complete/', 'POST', { version: e.version }); notify('Visit completed.'); await render(); }
    if (name === 'refresh') await render();
    if (name === 'provision') openForm('Provision a synthetic trainee', field('role', 'Approved role', [['nurse', 'Nurse'], ['clinician', 'Clinician'], ['registrar', 'Registrar'], ['reviewer', 'Privacy reviewer']]), 'Provision trainee', async d => { await api('/api/staff', 'POST', d); acceptSession(await api('/api/users/me/')); notify('Trainee provisioned without patient assignments.'); });
    if (name === 'probe') {
      if (!state.probe) return notify('Open Patient Alpha as the registrar first, then return to this clinician.', true);
      let result;
      try { await api('/api/patients/' + state.probe + '/'); result = 'Access allowed: this clinician currently has a valid assignment. Revoke it as registrar to test denial.'; }
      catch (error) { if (error.status !== 404) throw error; result = '404 · Record not available. The API denied access to an unrelated chart. Switch to Privacy reviewer and filter Denied to inspect the event.'; }
      const output = $('#probe-result'); output.className = 'restriction'; output.textContent = result;
    }
  }
  async function handleClick(event) {
    const b = event.target.closest('button'); if (!b || b.disabled) return;
    if (!state.user && b.dataset.route) return notify('Start the demo to explore the workspace.');
    if (b.dataset.route) { state.route = b.dataset.route; state.page = 1; state.search = ''; await render(); }
    if (b.dataset.switch) await switchPersona(b.dataset.switch);
    if (b.dataset.page) { state.page = Number(b.dataset.page); await render(); }
    if (b.dataset.patient) { state.page = 1; state.currentPatient = b.dataset.patient; state.route = 'patient-detail'; await render(); }
    if (b.dataset.encounter) { state.page = 1; state.currentEncounter = b.dataset.encounter; state.route = 'encounter-detail'; await render(); }
    if (b.dataset.action) await action(b.dataset.action);
    if (b.dataset.contact) { await api('/api/patients/' + b.dataset.contact + '/', 'PATCH', { contact: 'alternate', version: Number(b.dataset.version) }); notify('Synthetic contact updated.'); await render(); }
    if (b.dataset.revoke) { await api('/api/care-assignments/' + b.dataset.revoke + '/', 'DELETE'); notify('Assignment revoked.'); await render(); }
    const noteId = b.dataset.editNote || b.dataset.finalize || b.dataset.addendum;
    if (noteId) {
      const n = state.clinical.notes.find(note => note.id === noteId);
      if (b.dataset.editNote) openForm('Revise your draft', field('template', 'Replacement synthetic narrative', [['reviewed', 'Reviewed intake'], ['follow_up', 'Routine follow-up'], ['wellness', 'Wellness encounter']]), 'Save draft', async d => { await api('/api/notes/' + n.id + '/', 'PATCH', { template: d.template, version: n.version }); notify('Draft updated.'); });
      if (b.dataset.finalize) { if (!window.confirm('Finalize this synthetic note? Its content will be preserved; later corrections use addenda.')) return; await api('/api/notes/' + n.id + '/finalize/', 'POST', { version: n.version }); notify('Note finalized. Original content is now preserved.'); await render(); }
      if (b.dataset.addendum) openForm('Add a correction', '<p class="muted">The original note stays unchanged. A predefined synthetic clarification will be appended with your name and a timestamp.</p>', 'Add clarification', async () => { await api('/api/notes/' + n.id + '/addenda/', 'POST', { template: 'clarification', version: n.version }); notify('Addendum saved.'); });
    }
    if (b.dataset.editStaff) { const staff = state.staff.find(s => s.id === Number(b.dataset.editStaff)); openForm('Manage ' + staff.display_name, field('role', 'Approved role', [[staff.role, roles[staff.role]]].concat(Object.keys(roles).filter(r => r !== staff.role && r !== 'access_admin').map(r => [r, roles[r]]))) + field('active', 'Account status', staff.active ? [['true', 'Active'], ['false', 'Inactive']] : [['false', 'Inactive'], ['true', 'Active']], 'Disabling an account or changing its role revokes existing care assignments.'), 'Save access', async d => { await api('/api/staff/' + staff.id + '/', 'PATCH', { role: d.role, active: d.active === 'true' }); acceptSession(await api('/api/users/me/')); notify('Staff access updated.'); }); }
  }
  document.addEventListener('click', event => { handleClick(event).catch(error => notify(error.message, true)); });
  document.addEventListener('submit', event => { if (event.target.id === 'patient-search') { event.preventDefault(); const data = new FormData(event.target); state.search = data.get('search'); state.ordering = data.get('ordering'); state.page = 1; render(); } });
  document.addEventListener('change', event => { if (event.target.id === 'audit-filter') { state.outcome = event.target.value; state.page = 1; render(); } });
  $('#persona').addEventListener('change', async event => { event.target.disabled = true; try { await switchPersona(event.target.value); } catch (error) { notify(error.message, true); event.target.value = state.user.persona; } finally { event.target.disabled = false; } });
  $('#start-button').onclick = async function () { this.disabled = true; try { acceptSession(await api('/api/demo/start/', 'POST')); state.route = 'overview'; await render(); } catch (error) { notify(error.message, true); } finally { this.disabled = false; } };
  $('#close-dialog').onclick = () => dialog.close();
  $('#reset-button').onclick = async function () { if (!window.confirm('Start a fresh synthetic workspace? This expires your current demo; other reviewers are unaffected.')) return; this.disabled = true; try { acceptSession(await api('/api/demo/reset/', 'POST')); state.route = 'overview'; state.page = 1; state.search = ''; state.probe = null; await render(); notify('A fresh demo is ready.'); } catch (error) { notify(error.message, true); } finally { this.disabled = false; } };
  $('#logout-button').onclick = async () => { try { await api('/api/demo/logout/', 'POST'); showWelcome(); notify('Signed out.'); } catch (error) { notify(error.message, true); } };
  (async () => { try { acceptSession(await api('/api/users/me/')); state.route = state.user.role === 'reviewer' ? 'audit' : state.user.role === 'access_admin' ? 'staff' : 'overview'; await render(); } catch (error) { if (error.status !== 401 && error.status !== 403) notify('Start the local Django server to load the demo.', true); } })();
})();
