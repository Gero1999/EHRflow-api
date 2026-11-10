# EHRFlow API

A local clinical-workflow demo using fictional patients and staff.

## Run the demo

With Python 3.10 and Pipenv installed, run these commands from the repository root:

```bash
pipenv sync
pipenv run migrate
pipenv run start
```

`pipenv sync` installs the dependencies pinned in `Pipfile.lock`. `pipenv run migrate` creates `ehrflow/ehrflow.sqlite3` and its database tables. The database is generated locally and is not included in Git.

Open **http://localhost:8001/** and click **Explore the demo** to create the fictional patients, staff, and encounters automatically. No separate seed command or account is required.

For later runs, use `pipenv run start`. If you delete the database, run `pipenv run migrate` again before starting, then click **Explore the demo** to create fresh sample data. Starting the server alone does not create the database tables or restore deleted data. Python recreates its `__pycache__` and `.pyc` cache files automatically.

See the [project overview](ehrflow/README.md) and [setup and usage guide](ehrflow/docs/usage.md) for details.
