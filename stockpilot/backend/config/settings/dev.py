from .base import *  # noqa

DEBUG = True
SECRET_KEY = SECRET_KEY or "insecure-dev-only-key-do-not-use-in-production"
CORS_ALLOWED_ORIGINS = CORS_ALLOWED_ORIGINS or ["http://localhost:4200"]
CSRF_TRUSTED_ORIGINS = CSRF_TRUSTED_ORIGINS or ["http://localhost:4200"]
