#!/usr/bin/env bash
# Fuzz the API with Schemathesis against a live server on a separate QA database.
#
#   docker compose exec -T db createdb -U saas_starter saas_qa   # once
#   POSTGRES_DB=saas_qa python manage.py migrate
#   POSTGRES_DB=saas_qa python manage.py seed_qa --tenants 50 --projects 5
#   POSTGRES_DB=saas_qa DJANGO_THROTTLE_USER=1000000/min DJANGO_THROTTLE_ANON=1000000/min \
#     DJANGO_THROTTLE_AUTH=1000000/min DJANGO_AUTH_FAILURE_LIMIT=1000000 \
#     python manage.py runserver 127.0.0.1:8002 --noreload &
#   scripts/run_schemathesis.sh
set -euo pipefail
BASE_URL="${BASE_URL:-http://127.0.0.1:8002}"
exec schemathesis run "$BASE_URL/api/schema/" \
  --base-url "$BASE_URL" \
  --checks all \
  --auth qa-owner-0@example.com:Qa-Seed-Password-1 \
  -H "X-Org: qa-org-0" \
  --hypothesis-max-examples "${MAX_EXAMPLES:-50}" \
  --hypothesis-seed "${SEED:-20261007}" \
  --no-color "$@"
