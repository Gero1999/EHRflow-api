# EHRFlow: setup, API, and operations guide

[Project overview](../../README.md) · Run all commands from the repository root.

## 1. Run locally

### First setup after cloning

Prerequisites: Python 3.10 and Pipenv. If Pipenv is missing, install it with `python3.10 -m pip install --user pipenv` and ensure its executable is on your PATH. Installing dependencies requires internet access; running the demo uses local application data and assets.

Open a terminal in the cloned repository folder. On macOS/Linux:

```bash
export PIPENV_VENV_IN_PROJECT=1
pipenv sync
pipenv run migrate
pipenv run start
```

On Windows PowerShell:

```powershell
$env:PIPENV_VENV_IN_PROJECT = "1"
pipenv sync
pipenv run migrate
pipenv run start
```

`pipenv sync` installs the versions recorded in `Pipfile.lock`. `migrate` creates the local SQLite database and its tables. No database download, database server, `.env` file, or administrator account is required for the guided demo.

### Starting again after setup

From the repository root, run `pipenv run start`. Alternatively, on macOS/Linux:

```bash
.venv/bin/python manage.py runserver 127.0.0.1:8001
```

Open **http://localhost:8001/** and select **Explore the demo**. No username or password is needed for the guided demo. Stop the server with **Ctrl+C**.

Run `pipenv run migrate` again after pulling an update that includes new database migrations.

If the local database has been deleted, run `pipenv run migrate` before `pipenv run start`, then select **Explore the demo** to create fresh sample records. Starting the server alone does not create the database tables. Deleted records are not restored by migrations or demo setup. Python recreates its ignored `__pycache__/` directories and `.pyc` files automatically when needed.

EHRFlow is the only runnable application. Its code lives in `ehrflow/`; its database is **`ehrflow/ehrflow.sqlite3`**. The root `manage.py` launches this project.

### Where the demo data comes from

Selecting **Explore the demo** automatically creates a private demo workspace with:

- Three fictional patients: Patient Alpha, Patient Beta, and Patient Gamma.
- Two scheduled encounters and three care assignments.
- Six staff personas covering registration, nursing, two clinicians, privacy review, and access administration.

Notes and observations start empty so you can create them during the tour. A fourth fictional patient, Patient Delta, is available to register. The predefined data lives in [scenarios.py](../records/scenarios.py); [create_workspace()](../records/demo.py) writes the initial records to your local database. There is no separate seed command to run.

Your changes stay in your local database. **Reset demo** creates fresh sample records in a new workspace and expires your previous workspace. Workspaces also expire after 24 hours; start a new demo when that happens. Expired records remain on disk until you run the cleanup command in section 5.

The database is intentionally excluded from Git because it accumulates sessions, authentication data, and demo activity. Each person cloning the repository creates their own database and sample records using these steps.

## 2. Take the five-minute tour

1. **Registrar:** open Patient Alpha's record and encounter to see its care team. Register Patient Delta, schedule his visit, and assign a nurse and clinician.
2. **Nurse:** use the persona selector to become Nurse One. Open an assigned encounter and record a predefined observation.
3. **Clinician:** switch to Clinician One. Open the encounter, draft a note, revise it, and finalize it. Add a correction; the finalized text remains unchanged. Complete the visit after its notes are finalized.
4. **Other clinician:** switch to Clinician Two. On Overview, select **Test unrelated chart access**. Patient Alpha's ID is remembered from your earlier view; the API returns `404` unless you explicitly assigned Riley to Patient Alpha's encounter.
5. **Privacy reviewer:** switch to Privacy Reviewer, open **Access ledger**, and filter for denied events. Clinical note content is excluded.
6. **Access administrator:** switch to Access Administrator. Provision the synthetic trainee, change a staff role, or deactivate an account. Changing roles or disabling accounts revokes their care assignments.

Use **Reset demo** to create a fresh workspace. This expires only your previous workspace; it does not reset another reviewer's session. Old synthetic records remain until the explicit cleanup command runs.

The persona selector is a **demo-only capability** tied to the browser's server-side session and workspace. It is not a production login design. Token users cannot switch personas without that demo session. Every account has one role, and there is no superuser bypass in the clinical API.

## 3. What the implementation enforces

| Area | Behavior | Source |
| --- | --- | --- |
| Reviewer isolation | Every record belongs to a workspace; relationships are checked before reads, filters, counts, and writes. | [permissions.py](../records/permissions.py), [filters.py](../records/filters.py) |
| Clinical access | Nurse/clinician access requires an active, in-period encounter assignment. Registrars, reviewers, and access administrators cannot retrieve clinical content. | [views.py](../records/views.py), `ClinicalRead` |
| Field access | Nurses see observations and finalized summary metadata; no clinical note body or draft. Clinicians see their own drafts and finalized notes in assigned encounters. | [views.py](../records/views.py), `ClinicalRead` |
| Synthetic-only writes | API inputs select fixed patient, contact, observation, and narrative scenarios. Unknown fields, custom names, note bodies, ownership, and workspace IDs are rejected. No upload endpoint exists. | [scenarios.py](../records/scenarios.py), [serializers.py](../records/serializers.py) |
| Documentation integrity | Only the author can modify a draft, finalize it, or append a correction. Version checks reject stale writes. Finalized content cannot be replaced through the API. | [views.py](../records/views.py), `NoteDetail`, `NoteFinalize`, `AddendumList` |
| Audit | Record successful reads/writes and denials. Successful mutations and their events commit together. A failed required audit write prevents clinical data release or mutation. | [audit.py](../records/audit.py) |
| Session/token behavior | Sessions expire after 30 minutes of inactivity; workspaces expire after 24 hours. API tokens expire after 30 minutes, rotate at login, and can be revoked. | [settings.py](../config/settings.py), [authentication.py](../records/authentication.py) |
| Access administration | Role changes and deactivation revoke assignments; deactivation revokes tokens. Role, activity, and expiry are re-read on every request. | [permissions.py](../records/permissions.py), `StaffDetail` in [views.py](../records/views.py) |

The nurse's summary is deliberately limited metadata, not a claim that all nurses in real clinics should be denied note content. These are application-specific teaching policies. The policy page links the distinction between workforce access rules and HIPAA's treatment exception. Read the broader context in the [architecture and policy documentation](../docs/architecture.md).

## 4. API examples

The browser uses same-origin session cookies and CSRF protection. Changes require a CSRF header. The interface handles this automatically. It stores no bearer token in local storage.

Representative request bodies (replace IDs with values from your own workspace):

| Action | Method and route | JSON body |
| --- | --- | --- |
| Register synthetic patient | `POST /api/patients` | `{"scenario":"theo"}` |
| Schedule | `POST /api/encounters` | `{"patient":"<uuid>","reason":"intake"}` |
| Assign | `POST /api/care-assignments` | `{"encounter":"<uuid>","staff":7}` |
| Read chart | `GET /api/encounters/<uuid>/clinical/` | — |
| Record observation | `POST /api/encounters/<uuid>/observations/` | `{"kind":"pulse"}` |
| Draft note | `POST /api/encounters/<uuid>/notes/` | `{"template":"follow_up"}` |
| Revise draft | `PATCH /api/notes/<uuid>/` | `{"version":1,"template":"reviewed"}` |
| Finalize | `POST /api/notes/<uuid>/finalize/` | `{"version":2}` |
| Add correction | `POST /api/notes/<uuid>/addenda/` | `{"version":3,"template":"clarification"}` |
| Complete visit | `POST /api/encounters/<uuid>/complete/` | `{"version":2}` |
| Inspect denials | `GET /api/audit-events?outcome=denied` | — |

Use the latest returned `version`; example numbers are illustrative. UUID detail routes require a trailing slash; collection routes accept either form.

Patient lists accept `search`, `scenario`, `ordering=name` or `-name`, `page`, and `page_size`. Encounter lists accept `patient` UUID, `status`, `search`, and `ordering=scheduled_at`. The audit list accepts `outcome`, `role`, `action`, and time ordering. Page size defaults to 10, capped at 50. Inaccessible and nonexistent patient filter IDs both produce an empty scoped result.

Statuses: `201` for resource creation; `200` for successful reads/updates/deletes; `401` for missing/invalid/expired credentials; `403` for prohibited actions; `404` for inaccessible records; `400` for invalid input; `409` for stale versions or invalid state; `429` for throttling; `503` when required audit persistence is unavailable.

### Optional token exercise

Seeded demo accounts have **unusable passwords**. To enable a local credential exercise, obtain your workspace ID from `GET /api/users/me/`, then run:

```bash
.venv/bin/python manage.py demo_staff --workspace <workspace-uuid>
.venv/bin/python manage.py changepassword <printed-username>
```

Use that username/password with `POST /api/token/login/`, then `Authorization: Token <auth_token>`. `POST /api/token/logout/` revokes it. Passwords must pass Django's configured validators. Do not publish credentials. The 24-hour workspace limit still applies.

## 5. Verify and maintain

```bash
.venv/bin/python manage.py test records
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
node --check ehrflow/records/static/records/app.js
```

[Integration tests](../records/tests/test_api.py) exercise the full CSRF-protected session journey, cross-workspace access, unrelated charts, synthetic-input restrictions, role changes, audit failures, note states, version conflicts, and token expiry. They do not substitute for rendered browser, responsive-layout, or assistive-technology testing.

Back up the synthetic database to a new file, then restore into a disposable database for verification:

```bash
.venv/bin/python manage.py backup_demo ehrflow/backups/demo-01.sqlite3
.venv/bin/python manage.py check_backup ehrflow/backups/demo-01.sqlite3
```

The backup command refuses to overwrite files and creates private file permissions. Backups still contain staff, session/token, and audit data; keep them out of source control. The restore check verifies integrity and core record counts without changing the live database. This is a local recovery exercise, not an encrypted production backup strategy.

Expired workspaces can be inspected and explicitly removed:

```bash
.venv/bin/python manage.py purge_demo
.venv/bin/python manage.py purge_demo --execute
```

The second command deletes expired **demo records and audit history**. It is not a healthcare retention policy. It does not delete active workspaces.

## 6. Configuration and known limits

The root `.env` is loaded when using Pipenv. Direct `.venv/bin/python` commands read exported environment variables, not `.env` automatically. Configuration variables:

- `EHR_DEBUG=1` and loopback hosts are the local defaults.
- `EHR_SECRET_KEY` optionally supplies a private persistent key. Without one, restarting the server signs out browser sessions.
- `EHR_DEBUG=0` requires a secret, enables secure cookies, and redirects to HTTPS. It does not install a production server or configure hosting.

All normal application data is local. Assets use local files and system fonts; no analytics, remote fonts, email delivery, or external clinical API is used. Following the HHS documentation links intentionally opens an external website.

The current limits are explicit: local SQLite and process-local throttling; no clinical decision support, patient portal, export, emergency access, billing, FHIR, or production deployment. Audit records are protected through the API, not against a database operator. Token-login failure limits use process-local cache and are not distributed brute-force protection. Expired demo data needs the cleanup command. Dependency advisory checking remains pending; installed versions are pinned, not certified safe.

## 7. Portfolio evidence

- [Architecture and access model](../docs/architecture.md)
- [Risk register and incident exercise](../docs/risk-register.md)
- [API and session tests](../records/tests/test_api.py)

The next release step is browser/accessibility validation and screenshots, followed by a separate decision about hosting. This implementation has not been deployed.

## 8. Sharing the source

Share the application source, migrations, tests, documentation, `.env.example` templates, `Pipfile`, and `Pipfile.lock`. The bundled patient scenarios are fictional.

Keep local databases and backups, real credentials, `.env` files, virtual environments, and logs out of Git. The `.gitignore` covers these common local artifacts; check the staged files with `git diff --cached --name-only` and `git diff --cached` before committing. Ignore rules do not remove files already committed. Review screenshots separately for private data.

Publishing source does not deploy the app. Describe it as a synthetic-data portfolio prototype, not a clinical service or HIPAA-certified product. Dependency advisory review remains pending.
