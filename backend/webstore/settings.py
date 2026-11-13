import os
from pathlib import Path
import dj_database_url
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-this-secret-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions",
    "django.contrib.messages", "django.contrib.staticfiles",
    "store",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "store.middleware.CORSMiddleware",
]
ROOT_URLCONF = "webstore.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "webstore.wsgi.application"

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            ssl_require=True,
        )
    }
else:
    DATABASES = {
    "default": dj_database_url.config(
        default=os.environ.get("DATABASE_URL"),
        conn_max_age=600,
        ssl_require=True
    )
    }
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]
LANGUAGE_CODE = "fr-fr"
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "Africa/Lubumbashi")
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
PASSWORD_RESET_TIMEOUT = 3600
# E-mails transactionnels : Brevo est le fournisseur par défaut.
# L'expéditeur et la clé se changent dans les variables Render, sans code.
EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "brevo").strip().lower()
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "").strip()
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "WEB STORE").strip()
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "no-reply@webstore.local").strip()
REQUIRE_EMAIL_VERIFICATION = os.environ.get("REQUIRE_EMAIL_VERIFICATION", "true").lower() == "true"

def _env_int(name, default, minimum=1, maximum=86400):
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))

EMAIL_VERIFICATION_CODE_TTL_MINUTES = _env_int("EMAIL_VERIFICATION_CODE_TTL_MINUTES", 10, 1, 1440)
EMAIL_PASSWORD_RESET_CODE_TTL_MINUTES = _env_int("EMAIL_PASSWORD_RESET_CODE_TTL_MINUTES", 10, 1, 1440)
EMAIL_CODE_MAX_ATTEMPTS = _env_int("EMAIL_CODE_MAX_ATTEMPTS", 5, 1, 20)
EMAIL_RESEND_COOLDOWN_SECONDS = _env_int("EMAIL_RESEND_COOLDOWN_SECONDS", 60, 1, 3600)

# SMTP facultatif : EMAIL_PROVIDER=smtp pour utiliser cette configuration.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
if os.environ.get("EMAIL_HOST"):
    EMAIL_HOST = os.environ.get("EMAIL_HOST")
    EMAIL_PORT = _env_int("EMAIL_PORT", 587, 1, 65535)
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() == "true"
    EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "false").lower() == "true"
    if EMAIL_PROVIDER == "smtp":
        EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
