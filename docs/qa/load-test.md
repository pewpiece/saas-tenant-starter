# Load test results (Locust)

Script: [`loadtest/locustfile.py`](../../loadtest/locustfile.py). Each virtual
user is the owner of one of 50 seeded tenants (`manage.py seed_qa --tenants
50 --projects 5`) and lists, reads, creates and edits projects, reads
members, the plan and the audit log. Every list/detail response is checked
for rows of another tenant, and 1 in 17 requests deliberately sends another
tenant's `X-Org` (must be 403).

## Setup (local, single machine)

- Server: gunicorn, 4 sync workers, `DEBUG=False`, PostgreSQL 16 in Docker,
  throttles raised so they do not cap the run. Locust ran on the same
  12-core laptop, so absolute numbers are indicative only.
- Date: 2026-10-07. Raw CSVs: [`locust/`](locust/).

## Results

| Run | Users | Duration | Requests | Failures | req/s | Median | p95 | p99 |
|---|---|---|---|---|---|---|---|---|
| Saturation | 100 | 120 s | 2,499 | 0 | 20.85 | 4,300 ms | 4,900 ms* | 5,000 ms* |
| Below saturation | 10 | 60 s | 1,121 | 0 | 18.73 | 210 ms | 320 ms | 380 ms |

\* from the percentile table in [`summary-basic-auth.txt`](locust/summary-basic-auth.txt).

**Isolation under load:** 0 cross-tenant rows in 2,499 + 1,121 responses;
every foreign-`X-Org` probe (140 in the 100-user run) returned 403.

A first 100-user run had 3 failed creates (403 `plan_limit_reached`):
the earlier Schemathesis run had downgraded `qa-org-0` to Free. That was
test-data contamination, not a defect; the data was reseeded and the run
repeated (table above).

## Finding: HTTP Basic auth caps throughput (D-18, open)

Every Basic-authenticated request verifies the password with PBKDF2-SHA256
(720,000 iterations): **151 ms of CPU per request** (measured with
`check_password`, one core). With 4 workers the ceiling is about 26 req/s;
both runs sit at 19-21 req/s, and the fastest request seen was 166 ms. At 100
users the latency is almost entirely queueing behind password hashing.

Recommendation: issue tokens or sessions after one password check (e.g. DRF
`TokenAuthentication` or a login endpoint for session auth) and keep Basic
auth for scripts only. Lowering the hash cost is not an option.
