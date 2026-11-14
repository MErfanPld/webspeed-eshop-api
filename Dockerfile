# WebSpeed E-Shop API
FROM python:3.12-slim

ARG REQUIREMENTS=production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

WORKDIR /app

# psycopg[binary] and argon2-cffi ship wheels: no compiler needed
COPY requirements/ /app/requirements/
RUN pip install -r /app/requirements/${REQUIREMENTS}.txt

COPY . /app/

RUN adduser --disabled-password --gecos "" appuser \
    && mkdir -p /app/staticfiles /app/var \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "--access-logfile", "-"]
