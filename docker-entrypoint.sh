#!/bin/sh
# Apply migrations and seed on start (both idempotent), then run the given command.
set -e
# The Celery worker sets SKIP_MIGRATE=1 (the web container owns migrations).
if [ -z "${SKIP_MIGRATE}" ]; then
  python manage.py migrate --noinput
  python manage.py seed
fi
if [ "${DJANGO_SETTINGS_MODULE}" = "config.settings.production" ]; then
  python manage.py collectstatic --noinput >/dev/null
fi
exec "$@"
