"""
Apache Superset configuration for CLPM OPC-UA monitoring.
Mount as /app/pythonpath/superset_config.py inside the container.
"""
import os

# ─────────────────────────────────────────────────────────────
# Core
# ─────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "clpm-superset-secret-change-in-prod")
SQLALCHEMY_DATABASE_URI = os.environ.get(
    "SUPERSET_DB_URI",
    "postgresql+psycopg2://superset:superset_secret@192.168.18.90:5432/superset",
)

# ─────────────────────────────────────────────────────────────
# Feature flags for embedded dashboards & native filters
# ─────────────────────────────────────────────────────────────
FEATURE_FLAGS = {
    "EMBEDDED_SUPERSET": True,
    "DASHBOARD_NATIVE_FILTERS": True,
    "DASHBOARD_CROSS_FILTERS": True,
    "DASHBOARD_FILTERS_EXPERIMENTAL": True,
    "ENABLE_TEMPLATE_PROCESSING": True,
    "ALERT_REPORTS": True,
}

# ─────────────────────────────────────────────────────────────
# CORS – allow React app to embed dashboards
# ─────────────────────────────────────────────────────────────
ENABLE_CORS = True
CORS_OPTIONS = {
    "supports_credentials": True,
    "allow_headers": ["*"],
    "resources": {"/*": {"origins": "*"}},
}

# ─────────────────────────────────────────────────────────────
# Talisman (CSP) – allow iframe embedding from our origin
# ─────────────────────────────────────────────────────────────
TALISMAN_ENABLED = False   # Disable strict CSP to allow iframe embeds

WTF_CSRF_ENABLED = True
WTF_CSRF_EXEMPT_LIST = ["superset.views.core.log"]

# ─────────────────────────────────────────────────────────────
# Cache
# ─────────────────────────────────────────────────────────────
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/1")

CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_DEFAULT_TIMEOUT": 300,
    "CACHE_KEY_PREFIX": "superset_",
    "CACHE_REDIS_URL": REDIS_URL,
}

DATA_CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_DEFAULT_TIMEOUT": 60,
    "CACHE_KEY_PREFIX": "superset_data_",
    "CACHE_REDIS_URL": REDIS_URL,
}

# ─────────────────────────────────────────────────────────────
# Celery (for async queries & alerts)
# ─────────────────────────────────────────────────────────────
class CeleryConfig:
    broker_url  = REDIS_URL
    result_backend = REDIS_URL
    worker_prefetch_multiplier = 1
    task_acks_late = True

CELERY_CONFIG = CeleryConfig

# ─────────────────────────────────────────────────────────────
# Row limits
# ─────────────────────────────────────────────────────────────
ROW_LIMIT = 100_000
VIZ_ROW_LIMIT = 50_000
