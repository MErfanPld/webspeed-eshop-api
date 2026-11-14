#!/bin/sh
# Apply migrations and seed on start (both idempotent), then run the given command.
set -e
python manage.py migrate --noinput
python manage.py seed
if [ "${DJANGO_SETTINGS_MODULE}" = "config.settings.production" ]; then
  python manage.py collectstatic --noinput >/dev/null
fi
exec "$@"
