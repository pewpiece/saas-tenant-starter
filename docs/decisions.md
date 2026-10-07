# Design decisions (Milestone 1)

Ambiguous points, the simplest option chosen, and why.

- **Auth first, then tenant: 401 -> 400 -> 403.** Tenant resolution runs in
  `TenantScopedViewMixin`, after DRF authentication. No credentials or bad
  credentials -> 401 with a `WWW-Authenticate: Basic` challenge; missing
  `X-Org` -> 400; unknown slug or non-member -> one byte-identical 403, so
  the API never reveals whether a slug exists. *(Milestone 1 used a Django
  middleware here, which ran before DRF auth; see D-01/D-02/D-09 in
  defect-log.md.)*

- **`all_tenants` as the test-fixture creation path.** Tests need to create
  rows across multiple organizations without a request-scoped active
  tenant. Rather than inventing a separate test-only bypass, `ProjectFactory`
  uses the same `all_tenants` manager that's documented for admin/system use
  — one escape hatch, one thing to audit in QA.

- **No login/token endpoints.** Authentication endpoints (session login,
  token issuance, etc.) weren't in the Milestone 1 scope. Tests authenticate
  directly via DRF's `APIClient.force_authenticate`. `SessionAuthentication`
  and `BasicAuthentication` are wired in DRF settings so the app is usable
  as-is behind Django's session login / HTTP basic auth, but no endpoints
  are built in this milestone.

- **Deleting a user: their work stays, orgs never lose their last owner.**
  `Project.created_by` is `SET_NULL`, so a project belongs to its org, not
  to its creator. Deleting a user removes their memberships; it is refused
  (`LastOwnerError`) if they are the only owner of any org. Transfer
  ownership or delete the org first. *(Milestone 1 used CASCADE, which
  deleted the user's projects in every org: D-07.)*

- **Pagination and throttling defaults.** Page-number pagination, 20 per
  page, `?page_size=` capped at 100. Throttles: 30/min anonymous, 300/min
  per user (env-overridable). Failed Basic logins lock the client IP out for
  5 minutes after 10 failures. Counters use the default cache (per process
  with LocMemCache); a multi-worker deployment needs a shared cache.

- **Tenant scoping is opt-in per view, and fails closed.** A view becomes
  tenant-scoped by using `TenantScopedViewMixin`. A view that forgets it and
  touches `Model.objects` raises `NoActiveTenantError` (a 500) rather than
  returning cross-tenant rows. `/admin/` is not tenant-scoped; its model
  admins use `all_tenants` explicitly.

- **Project directory lives at `~/saas-tenant-starter`, not the literal cwd.**
  The task said "work in this empty directory," but the given working
  directory was the user's actual home directory (full of unrelated personal
  files), not empty. Created a dedicated project directory instead of
  scaffolding Django directly into `$HOME`.

- **While a tenant is active, no write may touch another tenant, through any
  manager.** `save()`/`delete()` reject rows of another organization even if
  they were loaded via `all_tenants`; `organization` is immutable after
  create. With no active tenant (system code, admin, factories) an explicit
  `organization` is required on create. `objects.raw()` is refused outright
  (it cannot be scoped); use `all_tenants.raw()` and filter explicitly.
