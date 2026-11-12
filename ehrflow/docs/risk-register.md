# EHRFlow: risk register and incident exercise

Scope: a local, synthetic-data portfolio. Ratings below are design judgments, not a formal organizational HIPAA risk analysis.

| Risk | Likelihood / impact before controls | Implemented control and evidence | Remaining limitation |
| --- | --- | --- | --- |
| Unrelated or cross-workspace chart access | Medium / high | Scoped queries, care assignments, negative tests for detail/list/filter/nested routes | Requires ongoing regression testing as routes are added. |
| Client supplies another owner or real clinical text | Medium / high | Strict allowlisted inputs; fixed server-generated synthetic content | Search strings remain user input; audit excludes them and development logs redact query strings. |
| Administrative user acquires clinical privileges implicitly | Medium / high | Explicit roles; no staff/superuser clinical bypass; role-change tests | Server/database operators remain trusted; demo persona switching is intentionally privileged within its own sandbox. |
| Stale edit or silent change to finalized note | Medium / high | Version checks, atomic transactions, immutable finalized API representation, addenda | A database operator can bypass application controls. |
| Missing or misleading audit evidence | Medium / high | Transactional mutation events, independent denial events, fail-closed clinical reads, audit-failure tests | SQLite is not tamper-proof; a total storage failure also prevents logging the denial. |
| Stolen session/token | Medium / high | CSRF, HttpOnly session cookie, 30-minute session inactivity and token expiry, explicit logout, deactivation | Local HTTP is for loopback testing only. No production MFA or identity provider. |
| Repeated login or workspace creation requests | Medium / medium | Dedicated login/demo IP throttles; ignore forwarded-IP headers | Process-local cache, not distributed protection; rate limiting is not a full abuse defense. |
| Database loss or disk exhaustion | Medium / medium | Snapshot/restore commands, capped synthetic scenarios, workspace expiry, dry-run cleanup | Cleanup must be run; no scheduled encrypted backups, disk monitoring, or production availability guarantee. |
| Vulnerable dependency | Unknown / potentially high | Dependency versions and hashes recorded in the lockfile | Current advisory audit remains incomplete. Hashes/version pins are not proof of safety. |
| Publicly exposed debug service | Medium / high | Loopback run command, separate EHR settings, secure-cookie/HTTPS settings outside debug | No deployment has been performed; production configuration and browser validation remain pending. |

## Incident exercise: unexpected chart access

1. As the unrelated clinician, request the known Patient Alpha record. Expect `404` with a denial event.
2. As privacy reviewer, filter the ledger to denied events and identify the actor, route action, resource reference, and request ID. Do not export clinical text into the investigation.
3. As access administrator, deactivate the account if this were an investigated misuse. Verify its token/session access fails and assignments remain revoked.
4. Preserve relevant audit evidence and configuration in the exercise record. Review the scope of activity and whether any data was actually returned.
5. Record corrective action and repeat the denied-access test. In a real incident, the organization would assess applicable breach/notification obligations; an alert alone does not determine reportability.

Use only synthetic cases. This exercise demonstrates investigation and containment mechanics, not a completed compliance program.

## Recovery exercise

Create a snapshot with `backup_demo`, then run `check_backup`. It restores to a temporary database, checks SQLite integrity, and reads core record counts. Inspect the output before treating a backup as usable. The live database is never replaced by this check. A real recovery plan would additionally specify authorization, encryption, recovery objectives, retention, monitoring, and a tested cutover procedure.
