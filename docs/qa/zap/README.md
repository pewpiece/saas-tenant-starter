# OWASP ZAP scans

Run on 2026-10-07 with `ghcr.io/zaproxy/zaproxy:stable` (Docker Desktop)
against gunicorn (4 workers, `DEBUG=False`, QA database `saas_qa`) reached
at `host.docker.internal:8003`. HTTP only (local), so transport findings
are expected; production settings force HTTPS (SSL redirect, HSTS, secure
cookies).

## Baseline (passive) scan: `/admin/login/`

`zap-baseline.py`. Report: [baseline-admin.html](baseline-admin.html),
console: [baseline-admin.txt](baseline-admin.txt).

**0 FAIL, 8 WARN, 59 PASS.**

| Alert | Triage |
|---|---|
| CSP header not set (10038), Permissions-Policy not set (10063), COEP missing (90004) | Real, low: hardening headers missing on HTML pages. D-20 (open). |
| Cookie no HttpOnly flag (10010) | `csrftoken` is readable by JS by Django's design; the session cookie is HttpOnly. Accepted. |
| User-controllable HTML attribute, potential XSS (10031) | `next` is reflected into a hidden input, escaped by Django templates. False positive. |
| Non-storable content (10049), authentication request identified (10111), session management response identified (10112) | Informational. |

## Active API scan (authenticated): OpenAPI schema

`zap-api-scan.py -f openapi` with `Authorization: Basic …` and
`X-Org: qa-org-1` injected through ZAP's replacer, so the active rules ran
as a tenant owner. 31 imported URLs, 77 URLs in total. Report:
[api-scan.html](api-scan.html), console: [api-scan.txt](api-scan.txt).

**0 FAIL, 4 WARN, 115 PASS.**

| Alert | Triage |
|---|---|
| SQL Injection (40018) x3: signup `email`, `organization_slug`; accept `first_name` | **False positive.** All three hits were 429 responses: the `auth` throttle (10/min) was not raised for this server, so ZAP's boolean true/false comparison saw 400 vs 429. Replayed without throttling, each true/false payload pair gives identical responses (`test_boundaries.py::test_signup_sql_boolean_payloads_behave_identically`, `::test_accept_sql_boolean_payloads_are_plain_data`). All queries go through the ORM, and `objects.raw()` is refused. |
| Authentication credentials captured (10105) x13 | Basic auth over plain HTTP in this local scan. Production redirects to HTTPS; see D-18 for moving clients to tokens. |
| Cross-Origin-Resource-Policy missing (90004) x10 | Hardening header; folded into D-20. |
| Unexpected Content-Type (100001) x44 | Django's HTML 404 page for unknown paths, and the intentional `text/csv` export. Informational. |
