# Design decisions (Milestone 1)

Ambiguous points, the simplest option chosen, and why.

- **Missing `X-Org` header -> 400, unknown/unauthorized org -> 403.** A
  missing header is a malformed request (client forgot something); an org
  that doesn't exist or that the user isn't a member of is treated
  identically (403) so the API never reveals whether a given slug exists.

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

- **Tenant middleware only guards `/api/` paths.** `/admin/` and other
  non-API paths are not tenant-scoped. This is a starter with a single
  tenant-aware API surface; if the Django admin is used for cross-tenant
  support/ops, it already bypasses `TenantOwnedModel.objects` filtering by
  using `all_tenants` directly, so it was left out of the header-based
  resolution entirely rather than giving it a false sense of tenant safety.

- **Project directory lives at `~/saas-tenant-starter`, not the literal cwd.**
  The task said "work in this empty directory," but the given working
  directory was the user's actual home directory (full of unrelated personal
  files), not empty. Created a dedicated project directory instead of
  scaffolding Django directly into `$HOME`.
