"""Settings for the local, single-process DalilSENSE research workspace."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dalilsense-local-development-only")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "dalilsense.dashboard",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "dalilsense" / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
# SQLite indexes completed runs (summary markdown + metadata) alongside the
# per-run JSONL files, which remain the reproducibility source of truth.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(os.environ.get("DALILSENSE_DB_PATH", BASE_DIR / "dalilsense.sqlite3")),
    }
}
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "dalilsense" / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
DALILSENSE_DATASET_DIR = Path(os.environ.get(
    "DALILSENSE_DATASET_DIR", BASE_DIR / "experiments" / "JSON_test"
))
DALILSENSE_RESULTS_DIR = Path(os.environ.get(
    "DALILSENSE_RESULTS_DIR", BASE_DIR / "experiments" / "results" / "exp1"
))
DALILSENSE_RUNS_DIR = Path(os.environ.get(
    "DALILSENSE_RUNS_DIR", BASE_DIR / "experiments" / "results" / "runs"
))
