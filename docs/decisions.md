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

- **Signup creates the org too.** `POST /api/auth/signup/` makes a user, an
  organization (slug from the name unless given), an owner membership and a
  Free subscription in one transaction. It rejects an email that already
  exists, which reveals that the email is registered: accepted for a
  starter (the alternative needs email verification).

- **Invitations.** Tokens are 32 random bytes, stored only as SHA-256, valid
  7 days, single use, revocable. One open invitation per email per org
  (DB constraint); an expired one is revoked automatically when re-inviting.
  Existing users accept by authenticating as the invited email; new users
  set a password on accept. Admins invite members/admins; only owners invite
  owners. The email is sent on commit through the console backend.

- **Member management.** Only owners change roles. Owners remove anyone,
  admins remove plain members, anyone can leave. The last owner can be
  neither demoted nor removed: 409 `last_owner`.

- **Plans.** Mock `Subscription` per org, Free (3 members incl. pending
  invitations, 5 projects) or Pro (unlimited, CSV export). Limit checks lock
  the org row. Downgrading while over a limit is allowed and deletes
  nothing: existing data stays readable and editable, creation is blocked
  until usage is back under the limit. Plan-limit and Pro-feature refusals
  are 403 with codes `plan_limit_reached` / `plan_upgrade_required`.

- **Audit log.** Tenant-owned and append-only at the ORM level (instances,
  querysets and managers refuse update/delete); rows go only when their org
  is deleted. Recorded explicitly in views (not signals) so the actor is
  known; `ATOMIC_REQUESTS` keeps a change and its entry in one transaction.
  Not enforced in the database (no trigger), so raw SQL could still alter it.

- **CSV export escapes formulas.** Cells starting with `= + - @ TAB CR` get a
  leading `'` to prevent CSV injection in spreadsheet apps.
