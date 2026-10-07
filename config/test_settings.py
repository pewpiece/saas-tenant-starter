"""Settings for the test suite.

Tests must not depend on a developer's .env: CI has none, and production
defaults (DEBUG off, HTTPS redirects, secure cookies) would break the test
client. Everything security-related is still exercised against the real
settings module by config/tests/test_deploy_settings.py.
"""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key-never-used-outside-the-test-suite")

from config.settings import *

SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0

# Fast hashing: tests create hundreds of users.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
