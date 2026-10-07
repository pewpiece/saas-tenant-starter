# SaaS Tenant Starter: weakness list

Reviewed at commit `2c24a39` (Milestone 1). Evidence for each item is in
`TEST_OUTPUT.txt` (sections 2 and 3).

**Summary:** the automated suite is green (32/32 tests pass, `ruff` is
clean, no missing migrations). The core isolation guarantee holds for the
HTTP API: cross-org list and detail requests return 403 or 404. The
weaknesses below are gaps the current tests do not cover.

| # | Severity | Weakness | Verified |
|---|----------|----------|----------|
| 1 | High   | Org slugs can be enumerated, which contradicts `docs/decisions.md` | Live curl |
| 2 | High   | The middleware's membership check is skipped for HTTP Basic auth | Live curl |
| 3 | High   | `TenantOwnedModel.save()` accepts any explicit `organization` and lets rows move between tenants | Shell |
| 4 | Medium | Insecure `SECRET_KEY` fallback, with no production hardening | `check --deploy` |
| 5 | Medium | Default manager raises on reverse relations and `dumpdata` | Shell |
| 6 | Medium | Admin has no models registered, so `docs/decisions.md` describes admin behaviour that doesn't exist | Shell |
| 7 | Low    | Deleting a user cascades across every org, and orgs can be left with no owner | Code review |
| 8 | Low    | No throttling, no pagination, and repeated membership queries | Code review |
| 9 | Low    | Unauthenticated requests get 403 instead of 401 | Live curl |
| 10 | Low   | Test coverage gaps | Code review |

---

### 1. Org slug enumeration (High)
`docs/decisions.md` says unknown orgs and non-member orgs are both treated
as 403 "so the API never reveals whether a given slug exists". The status
code is the same, but the response body differs:

| Request | Existing slug | Non-existent slug |
|---|---|---|
| Anonymous | `Authentication credentials were not provided.` | `Not a member of this organization.` |
| Basic auth, non-member | `You do not have permission to perform this action…` | `Not a member of this organization.` |
| Wrong password | `Invalid username/password.` | `Not a member of this organization.` |

**Cause:** [middleware.py:38-43](../../apps/tenants/middleware.py#L38-L43) rejects unknown slugs before
authentication runs. Known slugs pass through to DRF, which returns its
own messages.
**Fix:** for anonymous or non-member requests, return one identical
response whether or not the slug exists. One way is to defer the
"slug not found" rejection until after authentication, in a DRF
permission class.

### 2. Membership check in the middleware is bypassed under Basic auth (High, defence in depth)
DRF authenticates inside the view, not in Django middleware. So for any
request using `BasicAuthentication`, `request.user` is still
`AnonymousUser` when `TenantMiddleware` runs, and
[middleware.py:45-51](../../apps/tenants/middleware.py#L45-L51) skips the membership check. The tenant
context is then set for a user who isn't a member. Today
`ProjectRolePermission` re-checks membership, so this does not leak data.
However, any future view that uses `Project.objects` without that
permission class would expose the org's data to any authenticated user.
**Fix:** enforce membership in a DRF permission or authentication step
that all tenant-scoped views share, and don't rely on the middleware's
`request.user`.

### 3. `save()` does not enforce the active tenant (High)
[models.py:81-90](../../apps/tenants/models.py#L81-L90) only fills in `organization` when it is empty. With
acme active, `Project.objects.create(organization=beta, ...)` writes the
row into beta. Re-saving an existing row with a changed `organization`
moves it to another tenant. (`editable=False` only hides the field from
forms and serializers. It does not protect the model layer.)
**Fix:** in `save()`, raise if a tenant context is active and
`organization_id` differs from it, both on create and on update.

### 4. Insecure secret fallback and production settings (Medium)
[settings.py:14](../../config/settings.py#L14) falls back to a hard-coded `django-insecure-…` key, so a
deployment with a missing env var starts silently with a publicly known
key, which means sessions and other signed values can be forged.
`check --deploy` reports 5 warnings: HSTS, SSL redirect, SECRET_KEY,
insecure session cookie, insecure CSRF cookie. HTTP Basic auth is enabled
with nothing forcing HTTPS.
**Fix:** require `DJANGO_SECRET_KEY` (no default) when `DEBUG=False`, and
add the `SECURE_*` and `*_COOKIE_SECURE` settings.

### 5. Default manager breaks standard Django tooling (Medium)
Because `objects` raises with no active tenant, these fail outside a
request:
- `user.projects.all()` → `NoActiveTenantError` (reverse managers are built from the default manager)
- `manage.py dumpdata projects` → `CommandError`
- `ModelAdmin`, `loaddata`/serializers, and any code using `_default_manager`

**Fix:** set `Meta.base_manager_name` / `default_manager_name` to
`all_tenants` (keeping `objects` as the safe API manager), or give
system code an explicit way to enter a tenant context.

### 6. Admin does not match the docs (Medium)
`docs/decisions.md` says the admin "already bypasses
`TenantOwnedModel.objects` filtering by using `all_tenants` directly".
In fact every `admin.py` is empty, and only `auth.Group` is registered.
There is no way to manage users, orgs, memberships, or projects without a
shell. If someone later registers `Project` naively, it will crash
(see #5).
**Fix:** register the models with `get_queryset()` returning
`all_tenants`, or correct the doc.

### 7. Data lifecycle (Low)
- `Project.created_by` is `on_delete=CASCADE`. Deleting one user deletes their projects in every org they belong to, including projects other members depend on. (This is documented, but it causes cross-tenant data loss.)
- Nothing guarantees an org keeps at least one `owner` membership.

### 8. Scalability and abuse (Low)
- No DRF throttling, so Basic auth can be brute-forced at full speed.
- The project list is unpaginated (documented).
- Each request runs up to 3 queries just for tenancy: the org lookup, a membership `exists()`, then the membership `get()` again in the permission class. Caching the membership on the request would save the repeat lookup.

### 9. 401 vs 403 (Low)
Because `SessionAuthentication` is listed first, unauthenticated requests
return 403 with no `WWW-Authenticate` header, while the middleware
docstring says the permission classes return "the 401". Basic auth
clients won't be prompted for credentials.

### 10. Test gaps (Low)
- Every API test uses `force_authenticate`, so no test exercises the real Basic or session auth path through the middleware. That's why #1 and #2 aren't caught. `force_authenticate` only applies inside DRF, so the middleware sees `AnonymousUser` in every test: `test_user_without_membership_gets_403` passes because of `ProjectRolePermission`, and the middleware's membership branch ([middleware.py:46-51](../../apps/tenants/middleware.py#L46-L51)) is never executed by the suite.
- No test checks that the 403 response is identical for unknown vs. non-member slugs.
- No test for an explicit or changed `organization` on save (#3). The mass-assignment test covers create only, not PATCH/PUT. The role tests check only status codes, not whether the row was actually changed or deleted.
- `UserFactory` triggers 44 factory_boy `DeprecationWarning`s (set `skip_postgeneration_save=True`).
