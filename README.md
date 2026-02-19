# Coffee Shop Order Management API

Production-grade **FastAPI** backend for the **Trio technical challenge**: order management with PostgreSQL, JWT auth (RBAC), payment and notification integration, idempotency, and strict order status flow.

## Quick start (local with Docker)

```bash
# Start Postgres and app
docker compose up -d db app

# Run migrations and seed catalog (one-off)
docker compose --profile tools run --rm migrate
docker compose --profile tools run --rm seed
docker compose --profile tools run --rm seed-users

# API: http://localhost:8000
# Docs: http://localhost:8000/docs
```

**Default users (dev):**  
- Customer: `customer@example.com` / `customer123`  
- Manager: `manager@example.com` / `manager123`

## Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Postgres URL (async: `postgresql+asyncpg://...`) | `postgresql+asyncpg://coffee_user:coffee_pass@localhost:5432/coffee_shop` |
| `JWT_SECRET_KEY` | Secret for signing JWTs (min 32 chars) | *(set in production)* |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Token expiry | `30` |
| `PAYMENT_SERVICE_URL` | Trio payment endpoint | `https://challenge.trio.dev/api/v1/payment` |
| `NOTIFICATION_SERVICE_URL` | Trio notification endpoint | `https://challenge.trio.dev/api/v1/notification` |
| `SENTRY_DSN` | Sentry DSN (optional) | - |
| `APP_ENV` | Environment name | `development` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `API_PREFIX` | API path prefix | `/api/v1` |

See `.env.example` for a template.

## Database setup

1. Create DB and user (or use Docker):

```sql
CREATE USER coffee_user WITH PASSWORD 'coffee_pass';
CREATE DATABASE coffee_shop OWNER coffee_user;
```

2. Run migrations:

```bash
alembic upgrade head
```

3. Seed catalog and users:

```bash
export DATABASE_URL="postgresql+asyncpg://coffee_user:coffee_pass@localhost:5432/coffee_shop"
python -m scripts.seed_catalog
python -m scripts.seed_users
```

## Running the app locally (without Docker)

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
# Set DATABASE_URL and JWT_SECRET_KEY (and optionally .env)
alembic upgrade head
python -m scripts.seed_catalog
python -m scripts.seed_users
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Tests

```bash
# Postgres for tests (e.g. coffee_shop_test)
createdb coffee_shop_test
export TEST_DATABASE_URL="postgresql+asyncpg://coffee_user:coffee_pass@localhost:5432/coffee_shop_test"
export JWT_SECRET_KEY=test-secret

# Run migrations and seed for test DB
export DATABASE_URL="$TEST_DATABASE_URL"
alembic upgrade head
python -m scripts.seed_catalog

# Run tests
pytest tests -v
```

## API endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/v1/menu` | No | Full catalog (products + variations + prices) |
| POST | `/api/v1/auth/token` | No | Login → JWT (form: username=email, password=...) |
| POST | `/api/v1/orders` | Customer | Place order (use `Idempotency-Key` header) |
| GET | `/api/v1/orders/{id}` | User | Order details (customer: own only) |
| PATCH | `/api/v1/orders/{id}/status` | Manager | Update status (strict flow) |
| POST/PATCH/DELETE | `/api/v1/admin/products...` | Manager | Product CRUD |

- **Health:** `GET /health`  
- **Metrics:** `GET /metrics` (Prometheus)

## Architecture (summary)

### Database schema

- **users** – email, hashed_password, role (`customer` \| `manager`). Role is mirrored in JWT.
- **products** – name, base_price_cents.
- **product_variations** – product_id, name, price_change_cents (per-item price = base + change).
- **orders** – customer_id, status (enum: waiting → preparation → ready → delivered), total_cents, metadata.
- **order_items** – order_id, product_id, variation_id, quantity, unit_price_cents (snapshot at order time).
- **payments** – order_id, amount_cents, request/response JSON (audit).
- **notifications** – one row per status-change notification; response stored.
- **idempotency_keys** – key_hash (SHA-256 of header), order_id, payment_id, expires_at.

Indexes on foreign keys, status, created_at, and unique on idempotency key_hash.

### Idempotency

- `POST /orders` accepts optional header `Idempotency-Key`.
- Key is hashed (SHA-256) and stored in `idempotency_keys` with TTL (e.g. 24h).
- First request: create order + payment, store key → order_id/payment_id, return 201.
- Replay (same key): return existing order with 200, no second payment call.

### RBAC & JWT

- Login: `POST /api/v1/auth/token` (OAuth2 form) → JWT.
- JWT payload: `sub` (user id), `role` (`customer` \| `manager`), `exp`.
- **Manager:** all endpoints + PATCH order status.
- **Customer:** create orders, GET own orders only; cannot PATCH status.

Example decoded JWT (conceptually):

```json
{ "sub": "uuid-of-user", "role": "customer", "exp": 1234567890 }
```

### Payment & notification

- **Payment:** On `POST /orders`, before creating the order we `POST` to `PAYMENT_SERVICE_URL` with `{"value": total_cents}`. Order is created only if payment returns success (2xx). Full response is logged (secrets redacted) and stored in `payments.response_payload`. On failure we return **402 Payment Required** with provider response.
- **Notification:** On every successful status change (PATCH status), we `POST` to `NOTIFICATION_SERVICE_URL` with `{"status": "..."}`. Response is logged and stored in `notifications`. Notification failure does **not** revert the order; it is logged and stored for retry/debugging.

### Concurrency

- Status updates use `SELECT ... FOR UPDATE` on the order row so transitions are serialized and no race conditions on state.

### Run locally with Docker and migrations

```bash
docker compose up -d db
docker compose --profile tools run --rm migrate
docker compose --profile tools run --rm seed
docker compose --profile tools run --rm seed-users
docker compose up -d app
```

## Deployment (e.g. Kubernetes)

- Use env-based config (no secrets in code). Prefer a secrets manager for `JWT_SECRET_KEY` and DB URL.
- Run migrations as a Job or init container before starting the app.
- Use TLS in front of the app (ingress or load balancer).
- Optionally add rate limiting (e.g. Redis) and ensure CORS is tightened for production origins.
- **Sentry:** set `SENTRY_DSN` for error monitoring.
- **Metrics:** scrape `/metrics` with Prometheus.

## Reference

- Implementation follows the **Trio technical challenge** spec (menu items, payment/notification URLs, order status flow, idempotency, RBAC).

## Checklist (implemented vs manual review)

- [x] SQL DDL and Alembic migrations
- [x] Catalog seed script (Latte, Espresso, Macchiato, Iced Coffee, Donuts + variations)
- [x] FastAPI app with async, typed schemas, OpenAPI tags
- [x] JWT auth with role claim; login endpoint; hashed passwords (argon2)
- [x] RBAC: manager full access + PATCH status; customer create/read own orders
- [x] Order status flow and strict transitions (400 on invalid)
- [x] Payment integration (create order only on success; 402 on failure; log/store response)
- [x] Notification on status change; log and store response
- [x] Idempotency-Key for POST /orders; 200 replay
- [x] Validation and pricing; 409 on total mismatch if client sends total
- [x] Atomic order + payment in transaction; row-level lock for status
- [x] Prometheus metrics; structured logging; Sentry (env)
- [x] Tests (unit + integration with mocked payment/notification)
- [x] Dockerfile and docker-compose (Postgres, app, migrate/seed profiles)
- [x] GitHub Actions: lint (black/ruff/mypy), test, Docker build
- [ ] **Manual:** Set strong `JWT_SECRET_KEY` and DB credentials in production
- [ ] **Manual:** Configure CORS origins and rate limits for production
- [ ] **Manual:** TLS and secrets manager in deployment
