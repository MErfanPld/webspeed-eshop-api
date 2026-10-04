# WebSpeed E-Shop API

Backend foundation for the **WebSpeed E-Shop** platform.

This repository contains the Django + Django REST Framework backend.  
It is designed as a clean, production-ready foundation and does **not** include business features yet (products, orders, cart, etc.). Those will be added in later phases.

---

## Stack

| Technology              | Purpose                          |
|-------------------------|----------------------------------|
| Django 5.x              | Web framework                    |
| Django REST Framework   | REST API                         |
| PostgreSQL 16           | Database                         |
| Docker / Docker Compose | Containerization                 |
| drf-spectacular         | OpenAPI / Swagger documentation  |
| django-cors-headers     | CORS handling                    |
| django-environ          | Environment configuration        |

---

## Requirements

- Docker & Docker Compose
- (Optional for local non-Docker development) Python 3.12+, PostgreSQL 16

---

## Environment Variables

Copy the example file and adjust values:

```bash
cp .env.example .env
```

| Variable                 | Description                                      | Default (dev)                          |
|--------------------------|--------------------------------------------------|----------------------------------------|
| `SECRET_KEY`             | Django secret key                                | (required)                             |
| `DEBUG`                  | Enable debug mode                                | `True`                                 |
| `ALLOWED_HOSTS`          | Comma-separated allowed hosts                    | `localhost,127.0.0.1,web`              |
| `POSTGRES_DB`            | PostgreSQL database name                         | `webspeed`                             |
| `POSTGRES_USER`          | PostgreSQL user                                  | `webspeed`                             |
| `POSTGRES_PASSWORD`      | PostgreSQL password                              | `webspeed`                             |
| `POSTGRES_HOST`          | PostgreSQL host                                  | `db`                                   |
| `POSTGRES_PORT`          | PostgreSQL port                                  | `5432`                                 |
| `DATABASE_URL`           | Full database URL (used by django-environ)       | `postgres://webspeed:webspeed@db:5432/webspeed` |
| `CORS_ALLOWED_ORIGINS`   | Comma-separated allowed CORS origins             | `http://localhost:3000,...`            |
| `CORS_ALLOW_ALL_ORIGINS` | Allow all origins (never `True` in production)   | `False`                                |

> **Important:** Never commit the `.env` file.

---

## Docker Setup

### 1. Build & Start

```bash
docker compose build
docker compose up -d
```

### 2. Check services

```bash
docker compose ps
```

### 3. Run Django checks

```bash
docker compose exec web python manage.py check
```

### 4. Apply migrations

```bash
docker compose exec web python manage.py migrate
```

### 5. Create superuser (optional)

```bash
docker compose exec web python manage.py createsuperuser
```

---

## Database

- PostgreSQL runs in the `db` service.
- Data is stored in a **persistent Docker volume** (`postgres_data`).
- Connection is configured via environment variables / `DATABASE_URL`.

---

## Migrations

After any model change:

```bash
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
```

Initial migrations for the custom User model are included.

---

## Development

The development server is started automatically by Docker Compose:

```
http://localhost:8000
```

Useful commands:

```bash
# Django shell
docker compose exec web python manage.py shell

# Create superuser
docker compose exec web python manage.py createsuperuser

# Collect static (production-like)
docker compose exec web python manage.py collectstatic --noinput

# View logs
docker compose logs -f web
docker compose logs -f db
```

Settings modules:

- Development: `config.settings.development`
- Production: `config.settings.production`

---

## Swagger / OpenAPI

Interactive API documentation is available at:

| Endpoint       | Description              |
|----------------|--------------------------|
| `/api/docs/`   | Swagger UI               |
| `/api/schema/` | OpenAPI schema (JSON/YAML) |

After starting the stack open:

```
http://localhost:8000/api/docs/
```

---

## Health Check

```
GET /api/v1/health/
```

**Successful response (200):**

```json
{
  "status": "ok",
  "database": "ok"
}
```

**Database unavailable (503):**

```json
{
  "status": "error",
  "database": "unavailable"
}
```

---

## Project Structure

```
.
├── manage.py
├── config/
│   ├── settings/
│   │   ├── base.py          # Shared settings
│   │   ├── development.py   # Development overrides
│   │   └── production.py    # Production overrides
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── apps/
│   └── users/               # Custom User model + Health check
│       ├── models.py
│       ├── managers.py
│       ├── admin.py
│       ├── views.py
│       └── urls.py
├── requirements/
│   ├── base.txt
│   ├── development.txt
│   └── production.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## Custom User Model

Email is the primary identifier (`USERNAME_FIELD = "email"`).

Fields:

- `id`
- `email` (unique)
- `password`
- `first_name`
- `last_name`
- `is_active`
- `is_staff`
- `is_superuser`
- `created_at`
- `updated_at`

Django Admin is fully configured for the custom User.

---

## Notes for next phases

This repository currently contains **only the foundation**.  
The following are intentionally **not** implemented yet:

- Products / Categories
- Orders / Payments
- Cart
- Customer-facing APIs
- JWT Authentication
- Media storage
- CMS / Page Builder API
- Frontend integration

---

## License

Proprietary – WebSpeed project.
