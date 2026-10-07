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

- **`created_by` on_delete=CASCADE.** Simplest default; deleting a user
  deletes the projects they created. A real product would likely use
  `PROTECT` or `SET_NULL` plus an ownership-transfer flow, but that's beyond
  Milestone 1's scope.

- **Project list is unpaginated.** No `DEFAULT_PAGINATION_CLASS` is set, so
  `GET /api/projects/` returns a plain JSON array. Fine for a starter; a
  real multi-tenant app would paginate before this matters.

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
