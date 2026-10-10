"""
Django settings for config project (SaaS tenant starter, Milestone 1).
"""

from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
if env.bool("DJANGO_READ_DOT_ENV", default=True):
    environ.Env.read_env(BASE_DIR / ".env")

DEBUG = env.bool("DJANGO_DEBUG", default=False)

# Never fall back to a known key outside DEBUG: signed cookies, sessions and
# password-reset tokens would all be forgeable.
SECRET_KEY = env.str("DJANGO_SECRET_KEY", default="")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is False.")
    SECRET_KEY = "django-insecure-dev-only-key"

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.core",
    "apps.accounts",
    "apps.tenants",
    "apps.projects",
    "apps.billing",
    "apps.audit",
    "drf_spectacular",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env.str("POSTGRES_DB", default="saas_starter"),
        "USER": env.str("POSTGRES_USER", default="saas_starter"),
        "PASSWORD": env.str("POSTGRES_PASSWORD", default="saas_starter"),
        "HOST": env.str("POSTGRES_HOST", default="localhost"),
        "PORT": env.str("POSTGRES_PORT", default="5432"),
        # Each request is one transaction, so a change and its audit log
        # entry are committed (or rolled back) together.
        "ATOMIC_REQUESTS": True,
    }
}


AUTH_USER_MODEL = "accounts.User"


# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


REST_FRAMEWORK = {
    # Basic first: DRF takes the WWW-Authenticate challenge from the first
    # class, so unauthenticated requests get a proper 401 instead of a 403.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.core.authentication.ThrottledBasicAuthentication",
        "apps.core.authentication.BearerTokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.DefaultPagination",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_SCHEMA_CLASS": "apps.core.schema.TenantAwareAutoSchema",
    "DEFAULT_THROTTLE_RATES": {
        "anon": env.str("DJANGO_THROTTLE_ANON", default="30/min"),
        "user": env.str("DJANGO_THROTTLE_USER", default="300/min"),
        "auth": env.str("DJANGO_THROTTLE_AUTH", default="10/min"),
    },
}

# Invitations
INVITATION_TTL_HOURS = env.int("DJANGO_INVITATION_TTL_HOURS", default=7 * 24)
INVITATION_ACCEPT_URL = env.str(
    "DJANGO_INVITATION_ACCEPT_URL", default="http://localhost:8000/invitations/accept?token={token}"
)
EMAIL_BACKEND = env.str(
    "DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = env.str("DJANGO_DEFAULT_FROM_EMAIL", default="no-reply@saas-starter.local")

SPECTACULAR_SETTINGS = {
    "TITLE": "SaaS Tenant Starter API",
    "DESCRIPTION": (
        "Multi-tenant API. Tenant-scoped endpoints need authentication plus an "
        "`X-Org: <organization-slug>` header."
    ),
    "VERSION": "2.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "apps.core.schema.add_error_responses",
    ],
}

# Failed HTTP Basic logins per client IP before a temporary lockout (429).
AUTH_FAILURE_LIMIT = env.int("DJANGO_AUTH_FAILURE_LIMIT", default=10)
AUTH_FAILURE_WINDOW = env.int("DJANGO_AUTH_FAILURE_WINDOW", default=300)

# Lifetime of bearer tokens issued by POST /api/auth/token/.
AUTH_TOKEN_TTL_HOURS = env.int("DJANGO_AUTH_TOKEN_TTL_HOURS", default=24 * 14)


# Transport security. Defaults are strict whenever DEBUG is off; each one can
# be overridden from the environment (e.g. when TLS ends at a proxy).

SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=not DEBUG)
SESSION_COOKIE_SECURE = env.bool("DJANGO_SESSION_COOKIE_SECURE", default=not DEBUG)
CSRF_COOKIE_SECURE = env.bool("DJANGO_CSRF_COOKIE_SECURE", default=not DEBUG)
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=0 if DEBUG else 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=not DEBUG)
SECURE_HSTS_PRELOAD = env.bool("DJANGO_SECURE_HSTS_PRELOAD", default=not DEBUG)
if env.bool("DJANGO_BEHIND_TLS_PROXY", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

STATIC_URL = "static/"

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
