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

## Linting

```bash
ruff check .
```

## Using the API

Every request under `/api/` must carry an `X-Org: <organization-slug>`
header identifying the tenant, in addition to normal authentication
(session or HTTP basic auth). The authenticated user must have a
`Membership` in that organization, or the request is rejected with 403.

```bash
curl -u user@example.com:password \
  -H "X-Org: acme" \
  http://localhost:8000/api/projects/
```

Role matrix for `/api/projects/`:

| Role   | List/Retrieve | Create/Update | Delete |
|--------|:---:|:---:|:---:|
| member | yes | no  | no  |
| admin  | yes | yes | no  |
| owner  | yes | yes | yes |

See [docs/decisions.md](docs/decisions.md) for notes on ambiguous design
choices made along the way.
