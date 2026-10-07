# Test strategy

Project: SaaS Tenant Starter (Django + DRF, shared-schema multi-tenancy).
Scope of this strategy: Milestones 1 to 3 on branch `milestone-2-hardening`.

## 1. Objective

Show, with reproducible evidence, that one organization can never read or
change another organization's data, and that the product features (signup,
invitations, members, plans, audit log) behave as specified. Tenant
isolation outranks every other quality attribute: a feature bug annoys one
customer, an isolation bug leaks every customer's data.

## 2. Scope

**In scope:** the REST API under `/api/`, the ORM tenancy layer
(`TenantOwnedModel`, managers, querysets, `tenant_context`), authentication
and authorization, plan limits, invitations and email content, the audit log,
the Django admin's tenant handling, production settings, the OpenAPI
contract, performance under multi-tenant load.

**Out of scope:** a frontend (none exists), real email delivery and payments
(console and mock backends by design), browser security headers on HTML
pages other than the admin, infrastructure (TLS termination, backups),
database-level row security (not used in this design).

## 3. Risks, ranked

Likelihood (L) and impact (I) on a 1-3 scale; risk = L x I. The ranking
decides where the most test effort goes.

| # | Risk | L | I | Risk | Main mitigation in tests |
|---|------|---|---|------|--------------------------|
| 1 | Cross-tenant read via an endpoint (IDOR, list/search/export leak) | 3 | 3 | 9 | Generated isolation suite over every route and method; Locust isolation checks under load |
| 2 | Cross-tenant write through an ORM path that skips the tenant filter (`save`, `bulk_create`, `update`, `raw`) | 2 | 3 | 6 | Model-level guard tests; write-path probe script; mutation testing of `apps/tenants` |
| 3 | Authorization error (wrong role allowed) | 2 | 3 | 6 | Generated authorization matrix (5 roles x 19 actions) |
| 4 | Tenant context leaking between requests (contextvar not reset) | 1 | 3 | 3* | Reset-after-request and reset-on-exception tests; concurrent Locust run with isolation assertions |
| 5 | Org enumeration (different responses for real vs fake slugs) | 3 | 2 | 6 | Byte-identical response tests, including malformed headers |
| 6 | Invitation abuse (reuse, expiry, wrong account, wrong org) | 2 | 3 | 6 | State-transition tests on the invitation lifecycle |
| 7 | Plan limits bypassed or wrongly enforced (off by one, downgrade) | 2 | 2 | 4 | Boundary-value tests at each limit; downgrade scenarios |
| 8 | Org left without an owner | 2 | 2 | 4 | Last-owner tests via API, model and user deletion |
| 9 | Mass assignment of privileged fields | 2 | 3 | 6 | Mass-assignment tests on every write endpoint |
| 10 | Unhandled input -> 500 | 2 | 2 | 4 | Schemathesis fuzzing; error-guessing tests |
| 11 | Insecure production configuration | 2 | 3 | 6 | `check --deploy` in a clean process; secret-key tests |
| 12 | Audit trail tampering or gaps | 1 | 2 | 2 | Append-only tests; audit assertions in feature tests |
| 13 | Throughput collapse under load | 2 | 2 | 4 | Locust multi-tenant run |

\* Low likelihood with contextvars, but listed because a leak would affect
every endpoint at once.

## 4. Techniques

| Technique | Where it is applied |
|-----------|--------------------|
| **Equivalence partitioning** | Callers split into owner / admin / member / outsider / anonymous (`test_authorization_matrix.py`); orgs into Free / Pro; accept flow into new user / existing user / wrong user (`test_invitations.py`) |
| **Boundary value analysis** | Free plan at 4/5/6 projects and 2/3/4 members; invitation expiry at ±seconds; field lengths at 255/256 and local part 64/65; page sizes 0/1/100/101 (`test_plans.py`, `test_boundaries.py`) |
| **State transition testing** | Invitation: pending -> accepted / expired / revoked, plus every illegal transition (reuse, revoke accepted, re-invite after expiry). Membership: owner <-> admin <-> member with the last-owner constraint. Subscription: Free <-> Pro while under/over limits |
| **Error guessing** | Malformed `X-Org` and `Authorization` headers, malformed JSON, huge ids, SQL-looking input, CSV formula injection, case differences in emails and slugs (`test_boundaries.py`, `test_plans.py`) |
| **Decision tables** | Member removal (actor role x target role x self) in `test_members.py::test_removal_matrix` |
| **Generated / model-based tests** | Route discovery drives the isolation suite; the authorization matrix is data-driven; Schemathesis generates requests from the OpenAPI schema |
| **Negative and abuse testing** | Cross-tenant attacks by the most privileged outsider (owner of another org); token theft; brute force |
| **Mutation testing** | mutmut on `apps/tenants` to find weak assertions |
| **Load testing** | Locust, 50 tenants, isolation checks on every response |

## 5. Test levels and tools

| Level | What | Tool |
|-------|------|------|
| Unit / model | Managers, querysets, save/delete guards, context helper | pytest, pytest-django, factory_boy |
| API / integration | Every endpoint through real HTTP Basic and session auth (not `force_authenticate` for new tests) | DRF `APIClient` |
| Contract | OpenAPI schema validity and documented responses | drf-spectacular, Schemathesis |
| Security | Isolation suite, authorization matrix, deploy check, ZAP baseline | pytest, `manage.py check --deploy`, OWASP ZAP |
| Performance | Multi-tenant load | Locust + gunicorn |
| Test quality | Branch coverage, mutation score | pytest-cov, mutmut |
| Static | Lint | ruff |
| CI | lint, tests with coverage gate, schema drift | GitHub Actions |

## 6. Environments

- Local: Python 3.12, PostgreSQL 16 in Docker (port 5433), `config.test_settings`.
- QA server for fuzzing/load: separate database `saas_qa` seeded by
  `manage.py seed_qa`; throttles raised so they do not mask behaviour.
- CI: GitHub Actions `ubuntu-latest` with a `postgres:16` service.

## 7. Entry criteria

- The code builds, migrations apply, `ruff check .` is clean.
- Each defect fix starts from a committed failing test reproducing it.
- Test data comes from factories or `seed_qa`, never from a developer
  database.

## 8. Exit criteria

| Criterion | Target |
|-----------|--------|
| Automated tests | 100% pass, zero warnings |
| Isolation suite | Every discovered tenant route and method attacked; 0 leaks; planted IDOR detected |
| Authorization matrix | Every cell matches the specification |
| Branch coverage | >= 90% (CI gate) |
| Mutation testing (`apps/tenants`) | Every surviving mutant reviewed; behaviour-changing survivors killed or justified |
| Fuzzing | 0 server errors; all Schemathesis checks pass |
| Open defects | No open High; open Medium documented with a mitigation |
| Deploy check | `check --deploy --fail-level WARNING` clean |

## 9. Defect management

Every defect gets an ID in [defect-log.md](defect-log.md) with severity,
priority, steps to reproduce, expected vs actual, the failing test and the
fix commit. Tests are never weakened or deleted to make them pass; when a
test exposes a bug, the test is committed first and the fix follows in a
separate commit.
