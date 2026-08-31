"""Settings for the bookings Django project."""
import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Load backend/.env into the process environment for local development, so
# values (e.g. GOOGLE_CALENDAR_CLIENT_SECRET) survive a server restart in a
# fresh terminal instead of needing to be re-exported by hand each time.
# Real environment variables (e.g. set by a deployment platform) always win —
# setdefault() never overwrites a value that's already present.
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _key, _value = _line.split("=", 1)
        os.environ.setdefault(_key.strip(), _value.strip())

DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() == "true"

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "insecure-dev-only-key-do-not-use-in-production"
    else:
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is not true."
        )
ALLOWED_HOSTS = [host for host in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",") if host]

# M-2: the Google Calendar refresh token's encryption key, independent of
# SECRET_KEY (see booking/crypto.py for why). Comma-separated so an old key
# can be kept around during rotation — first key encrypts, all keys decrypt.
_calendar_token_key_raw = os.getenv("CALENDAR_TOKEN_KEY", "")
if _calendar_token_key_raw:
    CALENDAR_TOKEN_KEYS = [k.strip() for k in _calendar_token_key_raw.split(",") if k.strip()]
elif DEBUG:
    CALENDAR_TOKEN_KEYS = ["ZTWgMGeUPRAayCwzPduwuemG0x77zz9DTzkT8ZFdoRQ="]  # insecure dev-only key
else:
    CALENDAR_TOKEN_KEYS = []  # booking/crypto.py raises ImproperlyConfigured if this is ever used

INSTALLED_APPS = [
    "daphne",
    "django_filters",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    'corsheaders',
    "accounts",
    "clients",
    "booking",
    "dashboard",
    "resources",
    "payments",
    "notifications",
    "reports",
    "core",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [

    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "bookings.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "bookings.wsgi.application"
ASGI_APPLICATION = "bookings.asgi.application"

if os.getenv("DB_NAME"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["DB_NAME"],
            "USER": os.getenv("DB_USER", "postgres"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "5432"),
            "OPTIONS": {"sslmode": os.getenv("DB_SSLMODE", "require")},
        }
    }
else:
    # Local fallback; production/deployment mein PostgreSQL environment variables dein.
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    # F-3: raised from Django's default of 8. Per ASVS 6.2.5/6.2.7, length
    # + breach screening (below) is the modern guidance — deliberately not
    # adding character-composition rules or forced rotation.
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "accounts.validators.PwnedPasswordValidator"},  # F-3
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Karachi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Google OAuth 2.0 Web client ID. ID token ka audience isi ID ke against verify hota hai.
# Not secret (client IDs are public), but sourced from env for consistency with
# GOOGLE_CALENDAR_CLIENT_ID below.
GOOGLE_OAUTH_CLIENT_ID = os.getenv(
    "GOOGLE_OAUTH_CLIENT_ID", "646130636057-pvm4nt85umvm0gl2orld8ku7nbmlcert.apps.googleusercontent.com"
)

# Google Calendar sync — server-side OAuth (authorization code + refresh
# token) for the business account, reusing the same GCP project/OAuth client
# as Google Sign-In above but with a client secret + redirect URI added.
# Backend-only: never sent to the frontend.
GOOGLE_CALENDAR_CLIENT_ID = os.getenv("GOOGLE_CALENDAR_CLIENT_ID", GOOGLE_OAUTH_CLIENT_ID)
GOOGLE_CALENDAR_CLIENT_SECRET = os.getenv("GOOGLE_CALENDAR_CLIENT_SECRET", "")
GOOGLE_CALENDAR_REDIRECT_URI = os.getenv(
    "GOOGLE_CALENDAR_REDIRECT_URI", "http://localhost:8000/admin-tools/google-calendar/callback/"
)
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")

# H-6: number of reverse-proxy hops between the client and this app that are
# actually trusted to append their own observed IP to X-Forwarded-For — used
# below for REST_FRAMEWORK["NUM_PROXIES"] and by core/audit.py::get_client_ip
# (one source of truth for both, so throttling and audit-log IPs never
# disagree). Defaults to 1: a bare Azure App Service front-end, which
# appends the real connecting IP as the last comma-separated value. Without
# this, DRF's throttle identity — and our own logged/alerted IP — trusted
# the raw, entirely client-suppliable header value, so an attacker could
# defeat every anonymous-context rate limit (login, OTP, Google auth, MFA
# setup) by sending a different fake X-Forwarded-For on every request —
# confirmed by live testing (SecurityIssues.md H-6). Set this to match the
# real number of trusted hops if Azure Front Door / Application Gateway is
# ever added in front of App Service — setting it *higher* than the actual
# trusted hop count is dangerous (an attacker can pad the header with fake
# entries to land back on a client-controlled position), so when in doubt
# prefer leaving it low over raising it speculatively.
TRUSTED_PROXY_COUNT = int(os.getenv("TRUSTED_PROXY_COUNT", "1"))

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "NUM_PROXIES": TRUSTED_PROXY_COUNT,
     "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",

    ],
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "EXCEPTION_HANDLER": "core.exceptions.logging_exception_handler",
    # F-6: a baseline throttle on every endpoint, not just the three
    # auth-scoped ones — previously anything without an explicit
    # throttle_scope was completely unthrottled. Same caveat as H-5: these
    # limits are per-process until L-5 (a shared cache backend) is fixed.
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.ScopedRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "300/min",
        "google_auth": "10/min",
        "otp_request": "5/min",
        "otp_verify": "10/min",
        "login": "5/min",
        "token_refresh": "20/min",
        "booking_write": "20/hour",
        "pdf": "30/hour",
        "report": "60/hour",
        "mfa_setup": "10/hour",  # F-2: enrollment/confirm — not a hot path
    },
}
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake",
        "TIMEOUT": 300,  # Cache expiry time in seconds (e.g., 5 minutes)
    }
}
# In-process channel layer for real-time notification delivery (notifications app).
# Sufficient for a single-process dev/deployment; swap for channels_redis in a
# multi-process production deployment without changing any calling code.
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}
SIMPLE_JWT = {
    # M-1: shortened from 1 day. This bounds the damage window of a leaked
    # access token (e.g. M-3's now-fixed WebSocket-URL exposure, or any
    # future leak) to minutes instead of a full day. Safe to shorten now
    # that the frontend has a refresh-on-401 interceptor
    # (frontend/src/api/axiosInstance.js) — without that, this would log
    # users out mid-session instead of transparently refreshing.
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}
CORS_ALLOWED_ORIGINS = [
    origin for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",") if origin
]

# Origins allowed to make cross-site POSTs (e.g. /admin/ login) carrying a
# valid CSRF token. Must include the scheme (https://...).
CSRF_TRUSTED_ORIGINS = [origin for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if origin]

# Azure App Service (and most reverse proxies) terminate TLS at the edge and
# forward plain HTTP internally, setting this header to tell Django the
# original request was HTTPS.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Only require secure (HTTPS-only) cookies outside of local DEBUG development,
# so `runserver` over plain http:// keeps working.
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

# Base URL of the frontend SPA, used to build links embedded in emails (e.g. the
# waitlist "Book Now" link).
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000")

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
# SMTP transport — Brevo (smtp-relay.brevo.com:587, STARTTLS). All three are
# env-driven so a deployment (Azure App Service) overrides them without a
# code change; the defaults match the Brevo relay used in local dev.
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp-relay.brevo.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
# Django's own default is None (no timeout) — an unresponsive/slow SMTP
# handshake could otherwise block a request indefinitely. Bounds every
# outgoing email (OTP included) to a sane worst case instead.
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT_SECONDS", "10"))
# Brevo SMTP login + master key (NOT a mailbox password).
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
# Must be a sender identity verified in the Brevo account.
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", f"CRM & Booking <{EMAIL_HOST_USER}>")
# Reply-To for transactional mail (OTP). With Brevo the SMTP username is a
# relay login, not a real mailbox, so reply-to falls back to the verified
# From address rather than EMAIL_HOST_USER.
EMAIL_REPLY_TO = os.getenv("EMAIL_REPLY_TO", DEFAULT_FROM_EMAIL)
# From address for CRM-admin / security-alert mail (mail_admins, core/alerting.py,
# F-9). Kept a separate setting from DEFAULT_FROM_EMAIL so operational alerts can
# come from a distinct verified Brevo sender; defaults to DEFAULT_FROM_EMAIL when
# unset. Must also be a sender verified in the Brevo account.
SERVER_EMAIL = os.getenv("SERVER_EMAIL", DEFAULT_FROM_EMAIL)

# Real, owned destination for security alerts (SecurityFeatures.md F-9) —
# core/alerting.py routes rate-based and one-off security conditions here
# via Django's own mail_admins. Comma-separated email addresses; empty by
# default so alerting is a deliberate opt-in per deployment.
SECURITY_ALERT_EMAILS = [addr.strip() for addr in os.getenv("SECURITY_ALERT_EMAILS", "").split(",") if addr.strip()]
ADMINS = [(f"Security Alert Recipient {i + 1}", email) for i, email in enumerate(SECURITY_ALERT_EMAILS)]

# Structured JSON logging to stdout (SecurityFeatures.md F-1). Correct for a
# container on App Service, where stdout is what gets collected — a log file
# on the container's own disk is lost on every restart. The `security`
# logger carries authentication/authorization events (core/audit.py);
# `django` carries framework/operational logs as before.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "core.logging.JSONFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "security": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# Off-box log shipping (SecurityFeatures.md F-9, ASVS 16.4.3) — a log that
# only lives on the container is evidence an attacker (or an ordinary
# restart) can erase. Only added when an Azure Monitor / Log Analytics
# connection string is configured, so local dev and CI never need the
# `opencensus-ext-azure` package installed or reachable — declaring the
# handler class unconditionally would make Django try to import it on
# every startup regardless of whether it's actually used.
AZURE_LOG_ANALYTICS_CONNECTION_STRING = os.getenv("AZURE_LOG_ANALYTICS_CONNECTION_STRING", "")
if AZURE_LOG_ANALYTICS_CONNECTION_STRING:
    # opencensus-ext-azure's own self-telemetry ("statsbeat") makes a
    # synchronous network call during handler construction — confirmed by
    # hand to add ~9 extra seconds to every process boot (13s vs 4s) when
    # left on. It's Microsoft's own SDK-usage diagnostics, not anything
    # this app's monitoring depends on, so it's off by default. Must be set
    # before the handler below is constructed by dictConfig.
    os.environ.setdefault("APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL", "true")
    LOGGING["handlers"]["azure"] = {
        # core.logging.AzureLogHandler, not opencensus's own class directly
        # — see that module for why (a confirmed crash-on-every-log bug in
        # opencensus-ext-azure 1.1.15 that this wraps a fix around).
        "class": "core.logging.AzureLogHandler",
        "connection_string": AZURE_LOG_ANALYTICS_CONNECTION_STRING,
        "formatter": "json",
    }
    LOGGING["loggers"]["security"]["handlers"].append("azure")
    LOGGING["loggers"]["django"]["handlers"].append("azure")