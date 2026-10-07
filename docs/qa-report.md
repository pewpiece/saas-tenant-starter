# QA report: SaaS Tenant Starter, Milestones 1-3

Branch `milestone-2-hardening`, from Milestone 1 (2c24a39). Testing done
2026-10-07 on a local machine (Python 3.12.3, Django 5.0.14, DRF 3.15.2,
PostgreSQL 16 in Docker). Every number below comes from a command that was
run; raw outputs are linked.

## 1. Summary

- The Milestone 1 review listed 10 weaknesses. All 10 are fixed, each
  starting from a committed failing test.
- QA found 10 more defects: 3 high-severity ORM write-path bypasses, 4 found
  by Schemathesis, Locust, mutmut and ZAP, and 3 by feature and boundary tests.
- Of the 20 defects, **18 are fixed and 2 are open** (D-18 performance
  Medium, D-20 hardening headers Low). No High defect is open.
- Phase 2 added signup, invitations, member management, Free/Pro plans with
  limits, an append-only audit log, pagination, throttling and an OpenAPI
  schema.
- The suite grew from **32 to 456 tests**: all pass, zero warnings, branch
  coverage **97.85%**.
- Tenant isolation was attacked in five ways:
  - a generated suite over every route and method
  - a 95-cell authorization matrix
  - Schemathesis (1,050 generated requests, 0 server errors)
  - a 100-user, 50-tenant Locust run with an isolation check on every
    response
  - an authenticated ZAP active scan

  No cross-tenant access was found. A deliberately planted IDOR was caught
  by 5 tests.
- Mutation score on `apps/tenants` went from **64.2% to 78.8%** (83.7%
  excluding equivalent mutants). No surviving mutant affects isolation.

## 2. What was run

| Activity | Tool | Result | Evidence |
|---|---|---|---|
| Unit, API and integration tests | pytest, pytest-django, real Basic/session auth | 456 passed, 0 warnings | [qa/final-pytest-coverage.txt](qa/final-pytest-coverage.txt) |
| Branch coverage | pytest-cov | 97.85% (1,128 statements, 176 branches) | same |
| Generated isolation (IDOR) suite | pytest + URLconf discovery | 42/42; planted IDOR detected by 5 tests | [qa/isolation-suite-planted-idor.txt](qa/isolation-suite-planted-idor.txt) |
| Authorization matrix | pytest, data-driven | 95/95 cells match the spec | [qa/authorization-matrix.md](qa/authorization-matrix.md) |
| API fuzzing | Schemathesis 3.39.16, 7 checks, seed 20261007 | Run 1: 181 status-code conformance failures (D-17). Run 2: 1,050/1,050 on all 7 checks | [qa/schemathesis-run1-before-D17.txt](qa/schemathesis-run1-before-D17.txt), [qa/schemathesis-run2-after-D17.txt](qa/schemathesis-run2-after-D17.txt) |
| Load test | Locust 2.46.7, gunicorn x4 | 100 users / 50 tenants: 2,485 requests, 0 failures, 0 cross-tenant rows; ~21 req/s (D-18) | [qa/load-test.md](qa/load-test.md) |
| Mutation testing | mutmut 3.8.0 on `apps/tenants` | 651 mutants: 418 killed -> 656: 517 killed | [qa/mutation/README.md](qa/mutation/README.md) |
| Security scan | OWASP ZAP baseline + authenticated API scan | Baseline 0 FAIL / 8 WARN; API scan 0 FAIL / 4 WARN (SQLi alert = false positive, replayed in tests) | [qa/zap/README.md](qa/zap/README.md) |
| Production config | `manage.py check --deploy --fail-level WARNING` in a clean process | Passes (5 warnings at Milestone 1) | `config/tests/test_deploy_settings.py` |
| Write-path probe | `scripts/probe_write_paths.py` | Before: 3 bypasses; after: all refused | [milestone-1/probe_write_paths_before.txt](milestone-1/probe_write_paths_before.txt), [after](milestone-1/probe_write_paths_after.txt) |
| Live smoke test | runserver + curl | signup -> invite -> console email -> accept -> audit -> Pro export | [milestone-2-smoke.txt](milestone-2-smoke.txt) |
| Lint | ruff | clean | CI `lint` job |

Strategy, risks and techniques: [test-strategy.md](test-strategy.md).
Requirement coverage: [traceability-matrix.md](traceability-matrix.md)
(26 requirements: 25 pass, 1 partial).

## 3. Test counts

| Area | Tests | Highlights |
|---|---:|---|
| `apps/core` (cross-cutting QA suites) | 214 | authorization matrix 96, boundaries and error guessing 62, isolation suite 42, mass assignment 8, OpenAPI contract 5, seed 1 |
| `apps/tenants` | 144 | invitations, members, slug enumeration, membership enforcement, save guards, system access, admin, org switching, mutation findings |
| `apps/projects` | 30 | role permissions, isolation, write effects, API limits |
| `apps/billing` | 27 | plan limits, downgrade, Pro export |
| `apps/accounts` | 24 | user model, signup, user deletion, factories |
| `apps/audit` | 14 | append-only, recording, API |
| `config` | 3 | production settings |
| **Total** | **456** | Milestone 1 had 32 |

## 4. Coverage and mutation results

**Branch coverage: 97.85%** (CI gate: 90%). The remaining misses are
mostly unreachable defensive branches. Examples: `create_superuser` called
with `is_staff=False`, `ProjectRolePermission` without a resolved membership
(the mixin always sets one), and settings branches for `DEBUG` /
`DJANGO_BEHIND_TLS_PROXY` that only the subprocess deploy tests reach
(subprocesses are not measured).

**Mutation testing (`apps/tenants`):**

| Run | Mutants | Killed | Survived | No tests | Score |
|---|---:|---:|---:|---:|---:|
| 1 | 651 | 418 | 207 | 26 | 64.2% |
| 2 | 656 | 517 | 139 | 0 | 78.8% |

Run 1's survivors showed real blind spots:
- the last-owner check ignoring the organization
- `bulk_update`'s cross-tenant guard with no tests at all
- `pending()` filters
- audit entries losing actor and target
- the org row lock

All were killed in run 2. Writing those tests uncovered **D-19**. The 139
remaining survivors were all reviewed: 80 change only message wording, 21
are admin/CLI cosmetics, and 38 are equivalent. None changes tenant
ownership, visibility or whether a guard raises.

## 5. Defects found

Full records (steps, expected vs actual, failing test, fix commit):
[defect-log.md](defect-log.md).

| ID | Defect | Severity | Priority | Found by | Status |
|---|---|---|---|---|---|
| D-01 | Org slug enumeration (different 403 bodies/headers) | High | P1 | M1 review | Fixed |
| D-02 | Membership check skipped under HTTP Basic auth | High | P1 | M1 review | Fixed |
| D-03 | `save()` accepted a foreign org / moved rows between tenants | High | P1 | M1 review | Fixed |
| D-11 | `bulk_create` wrote into another tenant | High | P1 | Write-path probe | Fixed |
| D-12 | `update(organization=…)` moved rows across tenants | High | P1 | Write-path probe | Fixed |
| D-13 | `objects.raw()` returned every tenant's rows | High | P1 | Write-path probe | Fixed |
| D-04 | Insecure secret-key fallback; deploy check failing | Medium | P1 | M1 review | Fixed |
| D-05 | No safe system access; `dumpdata` crashed | Medium | P2 | M1 review | Fixed |
| D-06 | Admin had no models; docs inaccurate | Medium | P2 | M1 review | Fixed |
| D-07 | User deletion cascaded projects in every org; orgs could lose all owners | Medium | P2 | M1 review | Fixed |
| D-15 | Invitation without `role` -> 500 | Medium | P2 | Plan tests | Fixed |
| D-18 | Basic auth hashes the password on every request (~21 req/s) | Medium | P2 | Locust | **Open** |
| D-19 | Last-owner guard bypassed by an unsaved role change before `delete()` | Medium | P2 | Mutation testing | Fixed |
| D-08 | No pagination/throttling; Basic auth brute force | Low | P2 | M1 review | Fixed |
| D-14 | Schema generation crash from DRF's conditional-unique validator | Low | P2 | Deploy-check test | Fixed |
| D-09 | 403/400 instead of 401 for unauthenticated requests | Low | P3 | M1 review | Fixed |
| D-10 | Test gaps (no real auth, status-only assertions, warnings) | Low | P3 | M1 review | Fixed |
| D-16 | Email local part over 64 octets accepted | Low | P3 | Boundary tests | Fixed |
| D-17 | OpenAPI schema documented no error responses | Low | P3 | Schemathesis | Fixed |
| D-20 | No CSP / Permissions-Policy / COEP / CORP on HTML pages | Low | P3 | ZAP | **Open** |

By severity: 6 High, 7 Medium, 7 Low. By source: 10 from the Milestone 1
review, 3 from the write-path probe, 7 from testing activities.

## 6. Three ways tenant isolation could break, and how the tests catch them

**1. A view reads or writes through an unscoped query (classic IDOR).**
Someone writes `Project.all_tenants…` or a raw query in a view, or adds a
new endpoint and forgets tenant scoping.
- *Generated isolation suite*: every tenant route and method is attacked by
  an owner of another org with the victim's ids, bodies and query strings.
  Responses must not contain the victim's secret strings, and the victim's
  data is snapshotted before and after. Proven by planting exactly this bug:
  5 failures.
- *Route classification test*: fails when a new `/api/` route is neither
  tenant-scoped nor deliberately listed as public.
- *Fail closed by design*: `Model.objects` raises `NoActiveTenantError`
  outside a tenant, so a view without `TenantScopedViewMixin` returns 500
  instead of other tenants' rows.
- *Authorization matrix*: the `outsider` column (owner of another org) must
  be 403 on every tenant endpoint.

**2. An ORM write path skips the tenant guard.**
`bulk_create`, `bulk_update`, `QuerySet.update(organization=…)`, `raw()`,
saving a row loaded from another tenant, or re-pointing a row's
`organization`.
- *Save-guard tests* (`test_save_guards.py`) for every write path,
  including the three bypasses the probe found (D-11 to D-13).
- *Mutation testing* found that `bulk_update`'s guard had no tests at all;
  run 2 kills those mutants.
- *Isolation suite snapshot*: any write that lands in the victim org fails
  the test, whatever path produced it.

**3. The tenant context is resolved from the wrong source, or leaks.**
The tenant chosen before authentication (Milestone 1's middleware, D-02),
the `X-Org` header trusted without a membership check, the contextvar not
reset after a request or an exception, or responses that reveal which orgs
exist.
- *Membership enforcement tests* neutralise the role permission to simulate
  a careless future view: a non-member must still get 403, and the tenant
  context must never be set.
- *Byte-identical 403 tests* (unknown vs real slug, malformed headers) under
  Basic, session, anonymous and wrong-password requests.
- *Context reset tests*: after a normal request and after a view that
  raises. Plus *org-switching tests* with one client alternating `X-Org`.
- *Locust under concurrency*: 100 users across 50 tenants on 4 workers,
  each response checked for foreign rows, plus 140 foreign-`X-Org` probes.
  0 leaks, all probes refused.

## 7. Known remaining risks

1. **D-18, throughput.** HTTP Basic auth verifies the PBKDF2 password on
   every request (151 ms CPU). Production clients need tokens or sessions.
2. **D-20, browser hardening headers** missing on the admin and Swagger UI.
3. **Isolation is enforced in the application only.** Code that uses
   `all_tenants`, `all_tenants.raw()` or `connection.cursor()` bypasses it
   by design. PostgreSQL row-level security would add a second layer.
4. **Last-owner protection is model-level.** `Membership.objects.filter(…)
   .delete()` / `.update(role=…)` bypass it (no API path does this).
5. **Audit log immutability is ORM-level.** Raw SQL or a database admin can
   still change rows (no trigger).
6. **Throttle and lockout counters use LocMemCache** (per process). With
   several workers the effective limits multiply; a shared cache is needed.
7. **Signup reveals whether an email is registered.**
8. **Coverage limits of the dynamic testing:**
   - Schemathesis ran stateless, so for 6 operations (random ids, invitation
     acceptance) it only reached 4xx paths. Their success paths are covered
     by the unit suites, not by fuzzing.
   - The load test ran on one laptop with Locust on the same machine.
   - ZAP scanned over plain HTTP.
9. **CI runs on GitHub** (run 37648716663 on PR #1: lint, test with the
   90% coverage gate, and schema all passed). The workflow still uses
   `actions/checkout@v4` and `actions/setup-python@v5`, which GitHub flags
   as targeting the deprecated Node.js 20; bump them when newer majors are
   available.
