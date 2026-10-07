# Defect log

Every defect found in QA, with the failing test that reproduced it and the
commit that fixed it. D-01 to D-10 come from the Milestone 1 review
([milestone-1/WEAKNESSES.md](milestone-1/WEAKNESSES.md)); later IDs were
found while testing.

Severity: impact if exploited or hit. Priority: order to fix (P1 = before
any release).

| ID | Title | Severity | Priority | Test | Fix commit | Status |
|----|-------|----------|----------|------|------------|--------|
| D-01 | Org slug enumeration via differing 403 bodies/headers | High | P1 | `apps/tenants/tests/test_slug_enumeration.py` | f3a9e82 | Fixed |
| D-02 | Middleware membership check skipped under HTTP Basic auth | High | P1 | `apps/tenants/tests/test_membership_enforcement.py` | f3a9e82 | Fixed |
| D-03 | `save()` accepts a foreign organization and lets rows move between tenants | High | P1 | `apps/tenants/tests/test_save_guards.py` | 0b3c152 | Fixed |
| D-04 | Insecure SECRET_KEY fallback; `check --deploy` fails | Medium | P1 | `config/tests/test_deploy_settings.py` | 338c6e8 | Fixed |
| D-05 | No safe system-code path into a tenant; `dumpdata` crashes | Medium | P2 | `apps/tenants/tests/test_system_access.py` | dcc9e96 | Fixed |
| D-06 | No models registered in the admin; docs claimed otherwise | Medium | P2 | `apps/tenants/tests/test_admin.py` | 2101076 | Fixed |
| D-07 | Deleting a user cascades their projects in every org; orgs can lose their last owner | Medium | P2 | `apps/accounts/tests/test_user_deletion.py` | 9786e16 | Fixed |
| D-08 | No pagination or throttling; Basic auth brute-forceable; repeated membership queries | Low | P2 | `apps/projects/tests/test_api_limits.py` | b5d385e (+f3a9e82) | Fixed |
| D-09 | Unauthenticated requests get 403 (or 400) instead of 401 | Low | P3 | `apps/tenants/tests/test_unauthenticated.py` | f3a9e82 | Fixed |
| D-10 | Test gaps: no real-auth tests, status-only assertions, 44 factory warnings | Low | P3 | `apps/accounts/tests/test_factories.py`, `apps/projects/tests/test_write_effects.py` | a1df527 | Fixed |
| D-11 | `objects.bulk_create` writes rows into another tenant | High | P1 | `test_save_guards.py::test_bulk_create_*` | 0b3c152 | Fixed |
| D-12 | `objects.filter(...).update(organization=…)` moves rows to another tenant | High | P1 | `test_save_guards.py::test_queryset_update_cannot_move_rows_to_other_org` | 0b3c152 | Fixed |
| D-13 | `objects.raw()` returns every tenant's rows | High | P1 | `test_save_guards.py::test_raw_on_tenant_manager_is_refused` | 0b3c152 | Fixed |

---

## D-01: Org slug enumeration
- **Severity / priority:** High / P1
- **Steps to reproduce:** As a user who is not in `org-a`, send
  `GET /api/projects/` once with `X-Org: org-a` and once with
  `X-Org: no-such-org`. Repeat anonymously, with a wrong password, and with
  session auth.
- **Expected:** byte-identical responses (status, headers, body) for the
  real and the made-up slug.
- **Actual (Milestone 1):** both 403, but bodies differed
  (`You do not have permission…` / `Authentication credentials were not
  provided.` / `Invalid username/password.` vs `Not a member of this
  organization.`). Found during testing: even under session auth, where the
  bodies matched, the headers differed (Django `JsonResponse` from the
  middleware vs DRF `Response` with `Vary`/`Allow`), so the leak existed for
  every auth method.
- **Tests:** `test_basic_auth_nonmember_cannot_distinguish_real_slug[list|detail|create]`,
  `test_session_auth_nonmember_cannot_distinguish_real_slug[…]`,
  `test_anonymous_cannot_distinguish_real_slug`,
  `test_wrong_password_cannot_distinguish_real_slug`. Failing at 16bb221 (8/8).
- **Fix:** f3a9e82. Tenant resolution moved into `TenantScopedViewMixin`
  (after DRF auth). Unknown slug and non-member raise the same `NotAMember`
  exception.

## D-02: Membership check skipped under HTTP Basic auth
- **Severity / priority:** High / P1 (defence in depth; no data leaked in
  Milestone 1 because `ProjectRolePermission` re-checked membership)
- **Steps to reproduce:** Neutralise `ProjectRolePermission` (simulating a
  future view that forgets it). As a non-member of `org-a`, send
  `GET /api/projects/` with Basic auth and `X-Org: org-a`.
- **Expected:** 403, no `org-a` data, tenant context never set.
- **Actual (Milestone 1):** 200 with `org-a`'s projects. The middleware ran
  before DRF authentication, saw `AnonymousUser`, skipped the membership
  check and activated `org-a`.
- **Tests:** `test_basic_auth_nonmember_refused_even_without_role_permission`,
  `test_tenant_context_never_set_for_nonmember` (failing at 4d9261e);
  `test_session_auth_nonmember_refused_even_without_role_permission` (guard,
  passed already).
- **Fix:** f3a9e82. Membership is enforced in the shared DRF mixin for
  every auth method; the middleware is removed.

## D-03: `save()` does not enforce the active tenant
- **Severity / priority:** High / P1
- **Steps to reproduce:** With `org-a` active, call
  `Project.objects.create(name="x", organization=org_b, created_by=u)`;
  or load an `org-a` project, set `organization = org_b` and `save()`; or,
  with `org-a` active, `save()`/`delete()` a project loaded from `org-b`
  via `all_tenants`.
- **Expected:** `TenantMismatchError`; no row written to or changed in
  `org-b`.
- **Actual (Milestone 1):** the row was created in `org-b`, or moved to it.
  `editable=False` only hides the field from forms and serializers.
- **Tests:** `test_create_with_other_org_under_active_tenant_is_rejected`,
  `test_update_moving_row_to_other_org_under_active_tenant_is_rejected`,
  `test_update_moving_row_to_other_org_without_tenant_is_rejected`,
  `test_update_of_row_from_other_org_under_active_tenant_is_rejected`,
  `test_delete_of_row_from_other_org_under_active_tenant_is_rejected`.
  Failing at 7a4eef5.
- **Fix:** 0b3c152. `organization` is immutable after create; while a
  tenant is active, other orgs' rows cannot be created, saved or deleted.

## D-04: Insecure secret fallback, no production hardening
- **Severity / priority:** Medium / P1
- **Steps to reproduce:** Start with `DJANGO_DEBUG=False` and no
  `DJANGO_SECRET_KEY`; run `manage.py check --deploy --fail-level WARNING`.
- **Expected:** refuse to start without a key; deploy check clean with a
  production environment.
- **Actual (Milestone 1):** started with the public
  `django-insecure-dev-key-change-me`; `check --deploy` reported 5 warnings
  (W004, W008, W009, W012, W016).
- **Tests:** `test_missing_secret_key_with_debug_off_refuses_to_start`,
  `test_check_deploy_passes_with_production_environment` (failing at
  f394da4); `test_debug_on_still_starts_without_secret_key` (guard).
- **Fix:** 338c6e8.

## D-05: No safe system access; `dumpdata` crashes
- **Severity / priority:** Medium / P2
- **Steps to reproduce:** `manage.py dumpdata projects`; look for a
  supported way to run shell/command code as one tenant.
- **Expected:** dumpdata works; an explicit `tenant_context(org)` helper
  exists; reverse relations stay scoped (never fall back to all tenants).
- **Actual (Milestone 1):** `CommandError: Unable to serialize database:
  Project.objects was queried with no active tenant.`; only the raw
  `set_current_org`/`reset_current_org` token API existed.
- **Tests:** `test_tenant_context_*`, `test_dumpdata_*` (failing at
  48561a0); `test_reverse_relation_inside_tenant_context_never_leaks`
  (failed only because `tenant_context` did not exist);
  `test_all_tenants_is_not_the_default_manager` and
  `test_reverse_relation_outside_tenant_context_fails_closed` (guards).
- **Fix:** dcc9e96. `all_tenants` deliberately stays non-default.

## D-06: Admin unusable, docs inaccurate
- **Severity / priority:** Medium / P2
- **Steps to reproduce:** Log in to `/admin/` as a superuser.
- **Expected:** users, orgs, memberships and projects manageable; project
  list spans all orgs.
- **Actual (Milestone 1):** only `auth.Group` registered; registering
  `Project` naively would crash with `NoActiveTenantError`.
- **Tests:** `test_changelist_loads[…]`, `test_project_changelist_shows_every_org`,
  `test_project_change_page_loads`, `test_project_can_be_created_for_a_chosen_org`,
  `test_user_can_be_created_in_admin`. Failing at 5682c59 (8/8).
- **Fix:** 2101076. `TenantOwnedAdmin` reads via `all_tenants`.

## D-07: User deletion destroys other orgs' data; orgs can lose all owners
- **Severity / priority:** Medium / P2
- **Steps to reproduce:** Delete a user who created projects in two orgs;
  delete or demote the only owner of an org.
- **Expected:** projects kept (creator set to null); last-owner changes
  refused.
- **Actual (Milestone 1):** projects deleted in every org; last owner could
  be deleted or demoted.
- **Tests:** `test_deleting_user_keeps_projects_they_created_in_every_org`,
  `test_deleting_sole_owner_of_an_org_is_blocked`,
  `test_removing_last_owner_membership_is_blocked`,
  `test_demoting_last_owner_is_blocked` (failing at f69d074); three guards.
- **Fix:** 9786e16. Found while fixing: raising from the `pre_delete`
  signal poisons the caller's transaction (Django runs signals inside
  `atomic(savepoint=False)`), so the check runs in `User.delete()` first and
  the signal stays only as a backstop for bulk deletes.

## D-08: No pagination/throttling, Basic brute force, repeated queries
- **Severity / priority:** Low / P2
- **Steps to reproduce:** create 25 projects and list them; send many
  requests quickly; send repeated wrong Basic passwords; count membership
  queries per request with session auth.
- **Expected:** paginated (20, max 100); 429 when rates are exceeded; IP
  locked out after N failed logins; one tenancy query per request.
- **Actual (Milestone 1):** unpaginated array; no throttling; failed logins
  never reach DRF throttles (they run after authentication); 3 tenancy
  queries per request.
- **Tests:** `test_project_list_is_paginated`, `test_page_size_is_capped_at_100`,
  `test_authenticated_requests_are_throttled`,
  `test_failed_basic_auth_attempts_are_throttled_per_ip` (failing at
  1379bf2); `test_tenant_resolution_uses_one_membership_query` passed at
  1379bf2 because f3a9e82 had already fixed it.
- **Fix:** b5d385e (pagination, throttles, `ThrottledBasicAuthentication`)
  and f3a9e82 (single membership query).

## D-09: 403/400 instead of 401 for unauthenticated requests
- **Severity / priority:** Low / P3
- **Steps to reproduce:** `GET /api/projects/` with no credentials, with
  and without `X-Org`; and with a wrong Basic password.
- **Expected:** 401 with `WWW-Authenticate: Basic …`.
- **Actual (Milestone 1):** 403 with no challenge (`SessionAuthentication`
  was listed first), or 400 when `X-Org` was missing (the header was checked
  before authentication).
- **Tests:** `test_anonymous_with_header_gets_401_challenge`,
  `test_anonymous_without_header_gets_401_not_400`,
  `test_wrong_password_gets_401_challenge` (failing at 0f85d7e);
  `test_authenticated_without_header_gets_400` (guard).
- **Fix:** f3a9e82. `BasicAuthentication` listed first; authentication is
  checked before the header.

## D-10: Test gaps
- **Severity / priority:** Low / P3
- **Steps to reproduce:** run the Milestone 1 suite and read it.
- **Expected:** tests use real auth, check database effects, and run clean.
- **Actual (Milestone 1):** every API test used `force_authenticate`, so the
  middleware's membership branch never ran; role tests checked status codes
  only; mass assignment was checked on create only; 44 factory_boy
  `DeprecationWarning`s.
- **Tests:** `test_user_factory_emits_no_deprecation_warning` (failing at
  567c62b). New real-auth fixtures `basic_client` / `session_client`
  (e3e426d) and `test_write_effects.py` (DB state after denied writes, PATCH/PUT
  mass assignment, CSRF under session auth) pass at 567c62b: they close
  coverage gaps rather than reproduce a bug.
- **Fix:** a1df527. Suite runs with zero warnings.

## D-11: `bulk_create` bypasses tenant assignment
- **Severity / priority:** High / P1
- **Found by:** write-path probe (`scripts/probe_write_paths.py`, output in
  `milestone-1/probe_write_paths_before.txt`).
- **Steps to reproduce:** with `org-a` active,
  `Project.objects.bulk_create([Project(name="x", organization=org_b, created_by=u)])`.
- **Expected:** `TenantMismatchError`; rows without an org get the active org.
- **Actual:** row written to `probe-b`; rows without an org failed with an
  `IntegrityError` instead of being assigned.
- **Tests:** `test_bulk_create_cannot_write_into_other_org`,
  `test_bulk_create_assigns_active_org` (failing at 7a4eef5).
- **Fix:** 0b3c152 (`TenantQuerySet.bulk_create`; also `bulk_update`).

## D-12: `QuerySet.update` moves rows across tenants
- **Severity / priority:** High / P1
- **Found by:** write-path probe.
- **Steps to reproduce:** with `org-a` active,
  `Project.objects.filter(pk=p.pk).update(organization=org_b)`.
- **Expected:** refused.
- **Actual:** `(1, 'probe-b')`: the row moved to `org-b`.
- **Tests:** `test_queryset_update_cannot_move_rows_to_other_org[organization|organization_id]`
  (failing at 7a4eef5); `test_queryset_update_of_other_fields_stays_scoped` (guard).
- **Fix:** 0b3c152.

## D-13: `raw()` ignores the tenant filter
- **Severity / priority:** High / P1
- **Found by:** write-path probe.
- **Steps to reproduce:** with `org-a` active,
  `list(Project.objects.raw("SELECT * FROM projects_project"))`.
- **Expected:** refused (raw SQL cannot be scoped automatically).
- **Actual:** returned rows from every org.
- **Tests:** `test_raw_on_tenant_manager_is_refused` (failing at 7a4eef5).
- **Fix:** 0b3c152 (`UnscopedQueryError`; use `all_tenants.raw()`
  explicitly).
