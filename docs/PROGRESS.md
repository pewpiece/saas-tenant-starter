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

## Next

Phase 2: product features (signup, invites, member management, plans,
audit log, OpenAPI schema). Pagination and throttling from the Phase 2 list
were already delivered in Phase 1 (D-08).

## Open issues

- Throttle and lockout counters use LocMemCache (per process). A
  multi-worker deployment needs a shared cache.
- Last-owner protection is enforced by `Membership.save()/delete()` and a
  user `pre_delete` signal; `Membership.objects.filter(...).delete()` and
  `.update(role=...)` bypass it (no API path uses them).
