"""D-04: production settings must be safe by construction.

Each test starts a fresh `manage.py` process with a controlled environment
(the local .env file is ignored), because settings are evaluated at import.
"""

import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
STRONG_KEY = "k" * 10 + "Zq8#vL2@pX9!mN4$wR7%tY1^uI6&oP3*aS5(dF0)gH-jK+" + "x" * 10


def run_manage(*args, **env_overrides):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "SECURE_"))}
    env["DJANGO_READ_DOT_ENV"] = "False"
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "manage.py", *args],
        cwd=BASE_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_missing_secret_key_with_debug_off_refuses_to_start():
    result = run_manage("check", DJANGO_DEBUG="False")

    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY" in result.stderr


def test_debug_on_still_starts_without_secret_key():
    result = run_manage("check", DJANGO_DEBUG="True")

    assert result.returncode == 0, result.stderr


def test_check_deploy_passes_with_production_environment():
    result = run_manage(
        "check",
        "--deploy",
        "--fail-level",
        "WARNING",
        DJANGO_DEBUG="False",
        DJANGO_SECRET_KEY=STRONG_KEY,
    )

    assert result.returncode == 0, result.stdout + result.stderr
