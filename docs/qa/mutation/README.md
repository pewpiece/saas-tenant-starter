# Mutation testing: `apps/tenants`

Tool: mutmut 3.8.0 (`setup.cfg`), whole test suite available to every
mutant, run with `POSTGRES_PORT=5433 mutmut run --max-children 4`.

| Run | Mutants | Killed | Survived | No tests | Score (killed / all) |
|-----|---------|--------|----------|----------|---------------------|
| 1 (baseline) | 651 | 418 | 207 | 26 | 64.2% |
| 2 (after new tests and D-19 fix) | 656 | 517 | 139 | 0 | 78.8% |

Excluding the 38 equivalent mutants of run 2 (below), the score is
517 / 618 = 83.7%. The mutant count changed between runs because D-19's fix
added code and the unused `IsTenantOwner` class was removed.

Raw results: [run1-results.txt](run1-results.txt),
[run2-results.txt](run2-results.txt); diffs of every run-2 survivor:
[run2-survivor-diffs.txt](run2-survivor-diffs.txt).

## What run 1 revealed and what was done

New tests: `apps/tenants/tests/test_mutation_findings.py`.

| Surviving mutant (run 1) | Why it mattered | Status in run 2 |
|---|---|---|
| `_is_last_owner` without the organization filter | Owners of *other* orgs would satisfy the last-owner check | Killed |
| `Membership.save`: `and` -> `or` | Re-saving an unchanged last owner would raise | Killed |
| `_lock_organization` locking `pk=None` | Concurrent demotions could both pass the last-owner check | Killed (asserts the `FOR UPDATE` on the org row) |
| `TenantOwnedModel.save`: missing `_loaded_organization_id` treated as `None` | Rows created by `bulk_create` could not be saved again | Killed |
| `TenantQuerySet.bulk_update` (22 mutants, no tests) | The whole cross-tenant guard was untested | Killed (all behaviour mutants) |
| `pending()` without `accepted_at` / `revoked_at` filters | Accepted/revoked invitations would keep reserving plan seats | Killed |
| Re-invite clean-up without the `email` filter | Re-inviting one person would revoke everyone's expired invitations | Killed |
| Audit `record(...)` with `actor`/`target`/`changes` removed | Audit entries could lose who/what without any test failing | Killed |
| `_create_invited_user` ignoring names / password-similarity context | Weak passwords similar to the invitee's name/email accepted | Killed |
| `tenant_queryset` not detecting schema generation | OpenAPI generation would warn/crash | Killed |
| `IsTenantOwner` (4 mutants, no tests) | Dead code | Class removed |

Writing these tests also exposed a real bug, **D-19**: `Membership.delete()`
trusted the in-memory role, so an unsaved demotion followed by `delete()`
removed an org's last owner. Fixed in 6045a53.

## The 139 run-2 survivors, classified

Every survivor was reviewed (diffs in `run2-survivor-diffs.txt`).

| Category | Count | Examples | Decision |
|---|---|---|---|
| Error or help message wording | 80 | `"An organization must keep…"` -> `"XX…XX"`, upper/lower case, message replaced by `None` | Accepted: tests assert exception types, status codes, error *keys* and codes, not prose |
| Admin form/UI and CLI help text | 21 | admin field ordering, `disabled` flag on an already-immutable field, `--org` help text | Accepted: covered functionally by `test_admin.py`; cosmetic otherwise |
| Equivalent (no observable change) | 38 | `super().save(**kwargs)` dropping unused `*args`; `select_related(None)`; `False` -> `None` flags; `from_email=None` (Django falls back to `DEFAULT_FROM_EMAIL`); `_require_active_org(None)` after `get_queryset()` already raised | Not killable |

One equivalent mutant deserves a note: removing `accepted_at__isnull=True`
from the re-invite clean-up would stamp `revoked_at` on an *accepted*
invitation when a member who left is re-invited. `status` still reports
"accepted" (it checks `accepted_at` first), so nothing user-visible changes.

No surviving mutant changes which organization a row belongs to, who can
see it, or whether a guard raises.
