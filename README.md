# WebSpeed E-Shop API

Django + Django REST Framework backend for WebSpeed — a multi-store
e-commerce platform with a visual page builder. It replaces the frontend's
former Next.js `src/server` layer and keeps its paths, response shapes and
Persian error messages, so the frontend only needs a new base URL.

- **Stack:** Django 5.1, DRF 3.15, SimpleJWT, PostgreSQL 16, Redis 7, MinIO / S3 (django-storages), drf-spectacular
- **Docs:** Swagger UI at `/api/docs/`, OpenAPI schema at `/api/schema/`
- **Errors:** always `{"error": "<Persian message>", "details": <object|null>}`

## Quick start (Docker)

```bash
cp .env.example .env
```

```bash
docker compose up --build
```

On start the container runs `migrate` and `seed` (both idempotent). The seed
creates the default store, the owner account (`ADMIN_EMAIL` / `ADMIN_PASSWORD`;
in development without a password: `admin12345`), the default pages, 8
categories and 20 products.

- API: http://localhost:8000/api/v1/health
- Swagger: http://localhost:8000/api/docs/
- MinIO console: http://localhost:9001

Production: set real secrets in `.env` (`SECRET_KEY` ≥ 50 chars,
`CORS_ALLOWED_ORIGINS`, `ALLOWED_HOSTS`, S3 credentials, `ADMIN_PASSWORD`) and run

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Put a TLS reverse proxy in front of the API and set `TRUST_PROXY_HEADERS=True`
only behind it.

## Local development (without Docker)

```bash
python -m venv .venv && . .venv/bin/activate
```

```bash
pip install -r requirements/development.txt
```

```bash
export DJANGO_SETTINGS_MODULE=config.settings.development STORAGE_BACKEND=local SECRET_KEY=dev DATABASE_URL=postgres://webspeed:webspeed@localhost:5432/webspeed REDIS_URL=redis://localhost:6379/0
```

```bash
python manage.py migrate && python manage.py seed && python manage.py runserver
```

## Quality

```bash
ruff check .
```

```bash
DJANGO_SETTINGS_MODULE=config.settings.test python manage.py test tests
```

```bash
python manage.py spectacular --validate --fail-on-warn --file /tmp/schema.yml
```

CI (`.github/workflows/ci.yml`) runs lint, Django checks, migration check,
OpenAPI validation, tests (PostgreSQL + Redis), seeding twice and
`check --deploy` with production settings.

## Project structure

```
config/settings/{base,development,production,test}.py
apps/
  core/            errors, JWT header/cookie auth, validators, JSON-Schema block
                   validation, Redis rate limiting, pagination, seed (+ data/*.json)
  users/           custom User (email login, Argon2)
  authentication/  login · refresh · logout · me
  stores/          Store, StoreMember (owner/admin/editor), tenancy resolution
  pages/           builder pages: draft/publish, slug rules
  catalog/         Product, Category
  media/           MediaFile (public bucket)
  customers/       Customer (per store, by mobile)
  orders/          Order, checkout, tracking, private receipts
  stats/           dashboard
tests/             API tests (auth, tenancy, pages, catalog, media, orders)
```

`apps/core/data/block_definitions.json` and `seed.json` are exported from the
frontend sources (`src/builder/registry/block-definitions.ts`, `src/config/home-page.ts`,
`src/data/*`). Re-export them when block definitions change.

## Authentication

| Client | How |
|---|---|
| Bearer | `POST /auth/login` → `{access, refresh}`; send `Authorization: Bearer <access>`; `POST /auth/refresh {refresh}` |
| Browser (cookies) | Login also sets httpOnly `ws_access` / `ws_refresh` cookies. Use `credentials: "include"`. Unsafe requests authenticated by cookie must come from an origin in `CORS_ALLOWED_ORIGINS`/`CSRF_TRUSTED_ORIGINS` (Origin check = CSRF protection) |

- Access token 15 min, refresh 7 days; refresh tokens rotate and the old one is blacklisted. Logout blacklists the refresh token.
- Admin endpoints act on the **current store**: header `X-Store-Id` or cookie `ws_store` (set by `POST /admin/store {storeId}`), limited to stores the user belongs to; otherwise the user's first store.
- Roles: `editor` < `admin` < `owner`. Editors can edit pages, media and view orders; deleting pages/media and managing catalog, orders status and store settings need `admin`.
- Public storefront endpoints resolve the store from the `X-Store-Host` header (the storefront's host, sent by the frontend server) or `Host`, matching a store's custom `domain`; otherwise `DEFAULT_STORE_SLUG` or the first store.

## Endpoints (`/api/v1`)

| Method | Path | Auth | Request → Response |
|---|---|---|---|
| GET | `/health` | — | `{status, database}` |
| POST | `/auth/login` | — (8/15 min per IP+email) | `{email, password}` → `{user, access, refresh}` |
| POST | `/auth/refresh` | refresh | `{refresh?}` → `{access, refresh}` |
| POST | `/auth/logout` | — | `{refresh?}` → `{ok}` |
| GET | `/auth/me` | user | `{user, store, memberships}` |
| POST | `/auth/password` | user (5/15 min) | `{currentPassword, newPassword}` → `{ok, access, refresh}`; revokes all other sessions |
| GET | `/admin/store` | editor | `{store, role, memberships}` |
| PATCH | `/admin/store` | admin | `{name?, domain?, settings?}` → `{store}` |
| POST | `/admin/store` | member | `{storeId}` switch · `{create: {name, slug, domain?}}` → `{store, storeId}` |
| GET | `/admin/stores` | user | `{stores}` |
| GET | `/store` | — | `{store}` public info (contact, hours, Instagram, payment, shipping, theme) |
| GET / POST | `/admin/members` | member / owner | `{members, canManage}` · `{email, role, name?, password?}` → `{member}` |
| PATCH / DELETE | `/admin/members/<userId>` | owner | `{role}` → `{member}` · `{ok}` (a store always keeps one owner) |
| GET / POST | `/admin/pages` | editor | `{pages}` · `{name, slug, type?}` → `{page}` |
| GET / PUT / DELETE | `/admin/pages/<id>` | editor (DELETE: admin) | `{page}` · `{page: ManagedPage}` → `{page}` |
| POST | `/admin/pages/<id>/publish` · `/unpublish` · `/duplicate` | editor | `{page}` |
| GET | `/pages?id=…` or `?slug=…` | — | `{page}` (published snapshot only) |
| GET / POST | `/admin/products` | editor / admin | `{products}` · product → `{product}` |
| GET / PUT / DELETE | `/admin/products/<id>` | editor / admin | `{product}` |
| GET / POST | `/admin/categories` | editor / admin | `{categories}` · `{name, slug, image?, sort?}` → `{category}` |
| PUT / DELETE | `/admin/categories/<id>` | admin | `{category}` |
| GET | `/products?page&pageSize&category&gender&q&sort&featured&new&minPrice&maxPrice&ids` | — | `{products, pagination}` |
| GET | `/products/<slug>` · `/categories` | — | `{product}` · `{categories}` |
| GET / POST | `/admin/media` | editor | `{items}` · multipart `file` → `{item}` |
| DELETE | `/admin/media/<id>` | admin | `{ok}` |
| POST | `/orders` | — (10/10 min per IP) | multipart `data`=JSON `{customer, items[{productId,size,color,quantity}]}`, `receipt`=image → `{order: {number, total, status}}` |
| GET | `/orders/track?number&phone` | — (20/10 min per IP) | `{order}` (no personal data) |
| GET | `/admin/orders?status&q` | editor | `{orders}` |
| GET / PATCH | `/admin/orders/<id>` | editor / admin | `{order}` · `{status, note?}` → `{order}` |
| GET | `/admin/orders/<id>/receipt` | editor | `{url, expiresIn}` signed URL |
| GET | `/admin/customers` | editor | `{customers}` |
| GET | `/admin/stats?days=30` | editor | dashboard KPIs |
| POST | `/customer/otp/request` | — (3/10 min per phone, 10/10 min per IP) | `{phone}` → `{ok, expiresIn, isNew, devCode?}` |
| POST | `/customer/otp/verify` | — (5 attempts per code) | `{phone, code}` → `{customer, isNew}` + httpOnly `ws_customer` cookie |
| GET / PATCH | `/customer/me` | customer | `{customer, orders}` · `{name?, email?}` |
| POST | `/customer/logout` | — | `{ok}` |

Shapes (`ManagedPage`, `Product`, `Order`, …) are identical to the frontend
TypeScript types (camelCase); the full schema is in Swagger.

## Business rules (ported from the frontend `src/server`)

- **Pages:** slug normalization and validation, reserved routes (`/admin`, `/cart`, `/checkout`, `/products/*`, `/api/*`, `/_*`, …), unique slug per store, fixed slugs for `home` and header/footer layout documents, protected system pages, unique `-copy-N` slugs on duplicate, saving a draft never changes the published snapshot, layout documents are never routable.
- **Blocks:** validated against JSON Schemas generated from the frontend block registry (types, enums, responsive values, arrays), unknown types rejected, children only in container blocks, max nesting depth 4.
- **URLs:** `javascript:`, `data:`, `vbscript:`, `//host` … removed from all URL fields (`href`, `image`, `src`, …) in pages, products, categories and settings.
- **Orders:** server-side prices and shipping (`flatRate`, `freeOver`), variant validation, stock reserved with row locks in one transaction, cancellation restores stock and reopening reserves it again, tracking requires the buyer's phone, customers created/updated per store by phone.
- **Files:** type detected from magic bytes (PNG/JPEG/GIF/WEBP; SVG rejected), 5 MB limit; media in the public bucket, receipts in the private bucket served only through short-lived signed URLs.
- **Rate limits (Redis):** login (failed attempts only), checkout, tracking, OTP requests, password change.
- **Theme:** `settings.theme = {colors: {primary, primaryHover, accent, accentHover, background, surface, foreground, muted, mutedForeground, border, error: "#rrggbb"}, typography: {baseSize 12–22, lineHeight 1.2–2.2}}`, validated server-side.
- **Customers:** OTP codes are 6 digits, stored only as HMAC hashes in Redis for 2 minutes; sessions are signed, store-bound, httpOnly cookies (30 days). Orders placed with the same phone appear in the customer's profile.

## Frontend integration

The Next.js frontend (`webspeed-eshop`) proxies `/api/v1/*` (and `/media/*`) to
this API, so cookies are first-party. Its server components call
`API_INTERNAL_URL` directly with `X-Store-Host` and the forwarded cookies.
Configure `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` with the frontend
origin (e.g. `http://localhost:3000`).

## Environment variables

See `.env.example` (all variables are documented there).
