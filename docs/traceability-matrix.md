# Traceability matrix

Requirement -> test cases -> status. Test paths are relative to the
repository root; `::name` is a test function (parametrized cases count once
here). Status reflects the final run in [qa-report.md](qa-report.md).

| ID | Requirement | Test cases | Status |
|----|-------------|------------|--------|
| R-01 | Tenant resolved after authentication: no/bad credentials 401 with `WWW-Authenticate`, missing `X-Org` 400 | `apps/tenants/tests/test_unauthenticated.py` (4), `apps/core/tests/test_boundaries.py::test_malformed_authorization_headers_are_401` | Pass |
| R-02 | Unknown slug and non-member get byte-identical 403 | `apps/tenants/tests/test_slug_enumeration.py` (8), `test_boundaries.py::test_malformed_org_headers_are_refused_identically`, `test_tenant_isolation_suite.py::test_foreign_org_header_is_refused_like_unknown_slug` | Pass |
| R-03 | Membership enforced in one shared layer for every auth method | `apps/tenants/tests/test_membership_enforcement.py`, `test_tenant_resolution.py` | Pass |
| R-04 | No cross-tenant read or write through any API route (IDOR), including list/search/export | `apps/core/tests/test_tenant_isolation_suite.py` (42), `apps/projects/tests/test_isolation.py`, `test_write_effects.py::test_cross_org_update_and_delete_leave_row_untouched`, Locust isolation checks | Pass |
| R-05 | ORM rejects cross-tenant writes: `save`/`delete`, `bulk_create`, `bulk_update`, `update(organization=)`, `raw()` | `apps/tenants/tests/test_save_guards.py`, `test_mutation_findings.py::test_bulk_update_*` | Pass |
| R-06 | `all_tenants` is not the default manager; reverse relations scoped inside a tenant and fail closed outside | `test_system_access.py::test_all_tenants_is_not_the_default_manager`, `::test_reverse_relation_inside_tenant_context_never_leaks`, `::test_reverse_relation_outside_tenant_context_fails_closed` | Pass |
| R-07 | `tenant_context(org)` for system code; `dumpdata` works (`--org`); admin uses `all_tenants` | `test_system_access.py`, `test_admin.py`, `test_mutation_findings.py::test_dumpdata_unknown_org_is_a_clear_error` | Pass |
| R-08 | `DJANGO_SECRET_KEY` required when `DEBUG` is off; `check --deploy` clean | `config/tests/test_deploy_settings.py` | Pass |
| R-09 | Role matrix (owner/admin/member/outsider/anonymous x every action) | `apps/core/tests/test_authorization_matrix.py` (95 cells), [qa/authorization-matrix.md](qa/authorization-matrix.md) | Pass |
| R-10 | Signup creates user + organization + owner membership (+ Free plan) | `apps/accounts/tests/test_signup.py` | Pass |
| R-11 | Invitations: single-use, expiring tokens; console email; accept for new and existing users; correct org only | `apps/tenants/tests/test_invitations.py` (29), `test_mutation_findings.py` (token entropy, email content, re-invite scope) | Pass |
| R-12 | Member management: change role, remove, leave; at least one owner always | `apps/tenants/tests/test_members.py`, `apps/accounts/tests/test_user_deletion.py`, `test_mutation_findings.py::test_owners_of_other_orgs_*`, `::test_delete_checks_the_stored_role_not_the_unsaved_one` | Pass |
| R-13 | Deleted user's data: projects kept (creator nulled), never cascade across orgs; sole owner cannot be deleted | `apps/accounts/tests/test_user_deletion.py`, `test_audit_log.py::test_actor_email_survives_user_deletion` | Pass |
| R-14 | Users in several orgs switch via `X-Org` | `apps/tenants/tests/test_org_switching.py`, `test_signup.py::test_me_lists_every_org_of_the_user` | Pass |
| R-15 | Free plan limits: 3 members (incl. pending invitations), 5 projects; Pro unlimited | `apps/billing/tests/test_plans.py::test_free_project_limit_boundary`, `test_invitations.py::test_free_plan_*`, `test_boundaries.py::test_third_member_joins_fourth_is_refused` | Pass |
| R-16 | Pro-only feature gated (CSV export) | `test_plans.py::test_export_*` | Pass |
| R-17 | Downgrade over limit keeps data, blocks creation, warns | `test_plans.py::test_downgrade_*`, `::test_over_limit_org_can_edit_and_delete_but_not_create`, `::test_creation_resumes_once_back_under_the_limit` | Pass |
| R-18 | Audit log: tenant-owned, append-only, records create/update/delete and role changes | `apps/audit/tests/test_audit_log.py`, `test_members.py::test_owner_changes_a_role_and_it_is_audited`, `test_mutation_findings.py::test_*_audit_entr*` | Pass |
| R-19 | Pagination (20 default, max 100) | `test_api_limits.py::test_project_list_is_paginated`, `::test_page_size_is_capped_at_100`, `test_boundaries.py::test_pagination_edges` | Pass |
| R-20 | Throttling and Basic-auth brute-force lockout | `test_api_limits.py::test_authenticated_requests_are_throttled`, `::test_failed_basic_auth_attempts_are_throttled_per_ip` | Pass |
| R-21 | OpenAPI schema valid, documents `X-Org` and error responses, checked in and drift-checked | `apps/core/tests/test_openapi_contract.py`, `test_mutation_findings.py::test_schema_generates_without_warnings`, CI `schema` job, Schemathesis run 2 | Pass |
| R-22 | Mass assignment ignored on every write endpoint | `apps/core/tests/test_mass_assignment.py`, `test_mass_assignment.py` (projects), `test_write_effects.py` | Pass |
| R-23 | No unhandled input errors (no 500s) | Schemathesis (1050 generated requests, `not_a_server_error`), `test_boundaries.py` | Pass |
| R-24 | Acceptable performance with many tenants | Locust ([qa/load-test.md](qa/load-test.md)) | Partial: isolation holds under load, throughput capped by D-18 (open) |
| R-25 | CSV export safe against formula injection | `test_plans.py::test_export_neutralises_spreadsheet_formulas` | Pass |
| R-26 | Tenant context reset after every request, even on error | `test_tenant_resolution.py::test_context_var_resets_after_request`, `::test_context_var_resets_when_view_raises`, `test_org_switching.py` | Pass |
