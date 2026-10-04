# WebSpeed E-Shop API - Dockerfile
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements/base.txt /app/requirements/base.txt
RUN pip install --upgrade pip && \
    pip install -r /app/requirements/base.txt

# Copy project
COPY . /app/

# Create non-root user
RUN adduser --disabled-password --gecos "" appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Default command (overridden in docker-compose for development)
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
