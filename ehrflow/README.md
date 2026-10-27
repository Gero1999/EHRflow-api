# EHRFlow API

**Electronic Health Records · Django REST API · Role-Based Access Control**

A healthcare full-stack portfolio prototype demonstrating how patient registration, care-team access, clinical documentation, and audit review work together. Explore a patient visit through six staff roles in a browser interface backed by enforced API permissions. All data introduced is synthetic and fake.

![EHRFlow demo: patient registration, clinical documentation, and role-based access](docs/images/ehrflow-demo.gif)


## Differnet aspects considered for building the prototype

| Area | Implementation |
| --- | --- |
| Backend engineering | Django REST Framework, relational modeling, validated requests, filtering, pagination, and database migrations. |
| Authentication & authorization | Session and token authentication, CSRF protection, role-based access control (RBAC), care assignments, and workspace isolation. |
| Healthcare privacy | PHI classification concepts, task-specific access policies, and HIPAA minimum-necessary considerations documented alongside their limits. |
| Data integrity | Transactional audit events, version checks against stale edits, finalized notes, and append-only corrections. |
| Frontend development | HTML, CSS, and JavaScript interface for patient records, clinical workflows, staff administration, and access review. |
| Testing & operations | Integration tests for access denials and clinical workflows; database backup, restore verification, and expired-demo cleanup. |

**Stack:** Python 3.10 · Django · Django REST Framework · Djoser · django-filter · SQLite · Vanilla JavaScript · Pipenv

## Try it locally

With **Python 3.10** installed, open a terminal in the cloned repository folder and run:

```bash
python -m pip install --user pipenv
pipenv sync
pipenv run migrate
pipenv run start
```

Use `python3.10` instead of `python` if that is your Python 3.10 command. If Pipenv is already installed, skip the first line.

Open **http://localhost:8001/** and click **Explore the demo**. Fictional patients, staff, encounters, and care assignments are created automatically in your local database. No account, password, database download, or `.env` setup is needed.

**A quick tour:** register a patient and assign a care team; switch to a clinician to write and finalize a note; try an unrelated clinician's access; inspect the denial as a privacy reviewer. **Reset demo** starts a fresh workspace.

Stop with **Ctrl+C**. Start again with `pipenv run start`. See the [setup and usage guide](ehrflow/docs/usage.md) for Pipenv installation, platform-specific instructions, and the full walkthrough.

## Verify and explore

```bash
pipenv run test
pipenv run check
```

- [Architecture and role permissions](ehrflow/docs/architecture.md)
- [API examples, configuration, and maintenance](ehrflow/docs/usage.md)
- [Risk register and incident-response exercise](ehrflow/docs/risk-register.md)
- [Integration tests](ehrflow/records/tests/test_api.py)

## Scope

A local portfolio prototype using fictional records, not a clinical service or HIPAA-certified product. Persona switching is a demonstration feature. Production deployment, dependency advisory review, and browser/accessibility validation remain pending; see the risk register for limitations.
