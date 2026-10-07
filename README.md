# SaaS Tenant Starter

Milestone 1 of a multi-tenant SaaS starter in Django + DRF. Shared-schema
multi-tenancy: every tenant-owned table carries an `organization` foreign
key, and the active tenant is resolved per-request from an `X-Org` header.

## Stack

- Python 3.12, Django 5.x, Django REST Framework
- PostgreSQL (via docker-compose), settings read from environment variables
- pytest + pytest-django + factory_boy for tests
- ruff for linting

## Apps

- `apps.accounts` — custom `User` model (email login, no username).
- `apps.tenants` — `Organization`, `Membership`, the tenant-resolution
  middleware, and the `TenantOwnedModel` abstract base + manager that every
  tenant-owned model extends.
- `apps.projects` — `Project`, the first (and currently only) tenant-owned
  resource, exposed at `/api/projects/`.

## Setup

```bash
cp .env.example .env
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

docker compose up -d            # starts Postgres on localhost:5432
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Running tests

```bash
docker compose up -d
pytest
```

## System code and the admin

Tenant-owned models have two managers: `objects` (scoped to the active
tenant, raises if none is active) and `all_tenants` (unscoped, for admin
and system code only). To run shell or command code as one tenant:

```python
from apps.tenants.context import tenant_context

with tenant_context(org):
    Project.objects.all()   # only org's projects
```

`python manage.py dumpdata` works for all tenants; `dumpdata projects --org acme`
exports one tenant's tenant-owned rows. `/admin/` is a cross-tenant support
tool and reads through `all_tenants`.

## API schema

`openapi.yaml` is generated from the code and checked in. Regenerate it after
changing the API:

```bash
python manage.py spectacular --validate --fail-on-warn --file openapi.yaml
```

## Linting

```bash
ruff check .
```

## Using the API

Every tenant-scoped request under `/api/` needs normal authentication
(HTTP Basic or a Django session) **and** an `X-Org: <organization-slug>`
header naming the tenant. Tenant resolution happens after authentication:

| Situation | Response |
|---|---|
| No or bad credentials | 401 with `WWW-Authenticate: Basic` |
| Authenticated, no `X-Org` | 400 |
| Unknown slug, or not a member | 403 (identical for both, so slugs can't be probed) |
| Too many requests / failed logins | 429 |

```bash
curl -u user@example.com:password \
  -H "X-Org: acme" \
  http://localhost:8000/api/projects/
```

List endpoints are paginated (`count`, `next`, `previous`, `results`;
20 per page, `?page_size=` up to 100).

### Endpoints

| Endpoint | Tenant (`X-Org`) | Purpose |
|---|:---:|---|
| `POST /api/auth/signup/` | no | Create a user + organization (caller becomes owner, Free plan) |
| `GET /api/me/` | no | Current user and their organizations (valid `X-Org` values) |
| `POST /api/invitations/accept/` | no | Accept an invitation token (new users set a password) |
| `/api/projects/` (+ `/export/`) | yes | Projects; CSV export is Pro-only |
| `/api/members/` | yes | List members, change roles, remove, leave |
| `/api/invitations/` | yes | Invite by email, list, revoke |
| `GET/PATCH /api/subscription/` | yes | Plan, limits, usage; change plan (mock billing) |
| `GET /api/audit-log/` | yes | Append-only audit trail |
| `/api/schema/`, `/api/docs/` | no | OpenAPI schema and Swagger UI |

### Roles

| Action | member | admin | owner |
|---|:---:|:---:|:---:|
| List/retrieve projects, members, plan | yes | yes | yes |
| Create/update projects | no | yes | yes |
| Delete projects | no | no | yes |
| Export projects (Pro plan) | yes | yes | yes |
| Invite (member/admin) / revoke invitations | no | yes | yes |
| Invite an owner, change roles, change plan | no | no | yes |
| Remove a member | no | plain members | anyone |
| Leave the organization | yes | yes | yes (not the last owner) |
| Read the audit log | no | yes | yes |

### Plans (mock subscription)

| | Free | Pro |
|---|---|---|
| Members (incl. pending invitations) | 3 | unlimited |
| Projects | 5 | unlimited |
| CSV export | no | yes |

Downgrading while over a limit keeps all data; creating projects or adding
members is blocked until usage is back under the limit.

Invitation emails go to the console (`EMAIL_BACKEND` is the console backend
by default), so the accept link appears in the `runserver` output.

See [docs/decisions.md](docs/decisions.md) for notes on ambiguous design
choices made along the way.
