# Progress

Branch: `milestone-2-hardening` (off `master` at 2c24a39, Milestone 1).
Plan: the four phases in the task brief (hardening, product features, QA
cycle, final report).

## Phase 1: Hardening (done)

All 10 Milestone 1 weaknesses fixed test-first (failing test committed, then
the fix), plus 3 new defects found by probing ORM write paths (D-11 to
D-13). Details: [defect-log.md](defect-log.md).

- Tenant resolution moved from middleware into `TenantScopedViewMixin`
  (after DRF auth): 401 / 400 / byte-identical 403.
- `TenantOwnedModel` write guards: immutable organization, cross-tenant
  save/delete refused, `bulk_create`/`bulk_update`/`update`/`raw` guarded.
- `tenant_context(org)`, tenant-aware `dumpdata` (`--org`), admin for all
  models via `all_tenants`.
- Production settings: secret key required outside DEBUG,
  `check --deploy` clean.
- `created_by` SET_NULL; last-owner protection.
- Pagination, throttles, Basic-auth lockout.
- Real Basic/session auth fixtures; zero test warnings.

Result at end of phase: 100 tests pass, ruff clean.

## Phase 2: Product features (done)

- Signup (user + org + owner + Free plan) and `/api/me/` (org switching).
- Invitations: hashed single-use tokens, 7-day expiry, console email on
  commit, accept for new and existing users, revoke, org taken only from
  the invitation.
- Member management: role changes (owners), removal and leaving, last owner
  protected (409).
- Users in multiple orgs: tests for switching via X-Org (Basic + session).
- Plans: Free/Pro mock subscription, limits enforced with row locks, CSV
  export gated to Pro, downgrade keeps data and blocks creation.
- Append-only audit log of project create/update/delete, role changes,
  removals, invitations and plan changes; `GET /api/audit-log/`.
- Pagination and throttling (done in Phase 1, D-08); OpenAPI schema with
  drf-spectacular, checked in as `openapi.yaml`.
- Live smoke test of the whole flow: `docs/milestone-2-smoke.txt`.
- Defects found: D-14 (schema crash), D-15 (invite without role -> 500).

Result at end of phase: 213 tests pass, ruff clean, schema valid with
`--fail-on-warn`.

## Phase 3: QA cycle (done)

- [test-strategy.md](test-strategy.md), [traceability-matrix.md](traceability-matrix.md).
- Generated tenant isolation (IDOR) suite over every discovered route and
  method (42 cases; a planted IDOR is caught by 5).
- Generated authorization matrix: 5 roles x 19 actions, 95 cells, table in
  [qa/authorization-matrix.md](qa/authorization-matrix.md).
- Boundary, error-guessing and mass-assignment suites.
- Schemathesis: found D-17; final run 1,050/1,050 on all 7 checks.
- Locust: 100 users / 50 tenants, 0 failures, 0 cross-tenant rows; found
  D-18 (open).
- Coverage 97.85% (branch); mutmut on `apps/tenants` 64.2% -> 78.8%;
  found D-19.
- GitHub Actions workflow (lint, migrations check, tests with a 90%
  coverage gate, OpenAPI validity and drift).
- OWASP ZAP baseline and authenticated API scans (Docker available): found
  D-20 (open); the SQL injection alert was shown to be a false positive.
- Other defects found in this phase: D-16.

## Phase 4: Final report (done)

[qa-report.md](qa-report.md).

## State at the end

- 456 tests pass, 0 warnings, ruff clean, schema valid with `--fail-on-warn`.
- 20 defects logged: 18 fixed, 2 open (D-18 Medium, D-20 Low).

## Next (if work continues)

1. D-18: add token or session login so clients stop sending the password
   on every request.
2. D-20: add CSP / Permissions-Policy headers for the admin and Swagger UI.
3. Push the branch to GitHub and confirm the CI workflow runs green there.
4. Consider PostgreSQL row-level security as a second isolation layer.

## Open issues

- Throttle and lockout counters use LocMemCache (per process). A
  multi-worker deployment needs a shared cache.
- Last-owner protection is model-level; `Membership` queryset
  `.delete()`/`.update()` bypass it (no API path uses them).
- Audit log immutability is ORM-level only (no database trigger).
- Signup reveals whether an email is registered.
- Schemathesis ran stateless: success paths of id-based operations are
  covered by unit tests, not fuzzing.
