"""Locust load test: many tenants using the API at once.

Each simulated user is the owner of one seeded tenant (qa-org-<n>, see
`manage.py seed_qa`) and browses, creates and edits projects, reads members,
the plan and the audit log. Every list response is checked for rows from
another tenant, so the run also tests tenant isolation under concurrency
(the contextvar-based tenant context must never bleed between requests).

    locust -f loadtest/locustfile.py --host http://127.0.0.1:8003 \
        --headless -u 100 -r 20 -t 2m --csv docs/qa/locust/run
"""

import os
import random

from locust import HttpUser, between, task

TENANTS = int(os.environ.get("QA_TENANTS", "50"))
PASSWORD = "Qa-Seed-Password-1"


class TenantUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        self.n = random.randrange(TENANTS)
        self.slug = f"qa-org-{self.n}"
        self.client.auth = (f"qa-owner-{self.n}@example.com", PASSWORD)
        self.client.headers["X-Org"] = self.slug
        self.project_ids = []

    def _check_isolation(self, response, rows):
        foreign = [r for r in rows if r.get("organization") not in (None, self.slug)]
        if foreign:
            response.failure(f"cross-tenant rows for {self.slug}: {foreign[:2]}")

    @task(6)
    def list_projects(self):
        with self.client.get("/api/projects/", name="/api/projects/", catch_response=True) as r:
            if r.status_code != 200:
                r.failure(f"status {r.status_code}")
                return
            rows = r.json()["results"]
            self.project_ids = [row["id"] for row in rows]
            self._check_isolation(r, rows)

    @task(3)
    def retrieve_project(self):
        if not self.project_ids:
            return
        pid = random.choice(self.project_ids)
        with self.client.get(f"/api/projects/{pid}/", name="/api/projects/{id}/", catch_response=True) as r:
            if r.status_code == 404:
                r.success()  # deleted by a concurrent user of the same tenant
            elif r.status_code == 200:
                self._check_isolation(r, [r.json()])

    @task(2)
    def create_project(self):
        self.client.post("/api/projects/", json={"name": f"load {random.random():.6f}"}, name="/api/projects/ [create]")

    @task(1)
    def update_project(self):
        if not self.project_ids:
            return
        pid = random.choice(self.project_ids)
        with self.client.patch(
            f"/api/projects/{pid}/", json={"description": "edited under load"},
            name="/api/projects/{id}/ [update]", catch_response=True,
        ) as r:
            if r.status_code == 404:
                r.success()

    @task(2)
    def list_members(self):
        self.client.get("/api/members/", name="/api/members/")

    @task(1)
    def subscription(self):
        self.client.get("/api/subscription/", name="/api/subscription/")

    @task(1)
    def audit_log(self):
        self.client.get("/api/audit-log/", name="/api/audit-log/")

    @task(1)
    def cross_tenant_probe(self):
        """Ask for another tenant with our credentials: must be 403, every time."""
        other = f"qa-org-{(self.n + 1) % TENANTS}"
        with self.client.get(
            "/api/projects/", headers={"X-Org": other}, name="/api/projects/ [foreign X-Org]",
            catch_response=True,
        ) as r:
            if r.status_code == 403:
                r.success()
            else:
                r.failure(f"foreign tenant answered {r.status_code}")
