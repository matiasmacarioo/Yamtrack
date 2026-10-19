from fakeredis import FakeRedisConnection

from .settings import *  # noqa: F403

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,  # noqa: F405
        "TIMEOUT": 18000,  # 5 hours
        "OPTIONS": {
            "CONNECTION_POOL_KWARGS": {"connection_class": FakeRedisConnection},
        },
    },
}

CELERY_TASK_ALWAYS_EAGER = True

TESTING = True

# The optional *arr integrations read their configuration from the environment.
# Keep them disabled here so a developer's local .env cannot change test
# behaviour; the integration tests opt in explicitly via override_settings.
SONARR_ENABLED = False
RADARR_ENABLED = False

# Steam API key for testing
STEAM_API_KEY = "test_steam_api_key"
