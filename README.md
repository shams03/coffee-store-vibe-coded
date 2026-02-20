# Coffee Shop Order Management API

A production-grade REST API for managing a coffee shop's orders, built for the Trio technical challenge. Covers everything from menu browsing and order placement to payment processing, status tracking, and customer notifications — with security and reliability treated as first-class concerns throughout.

**Problem Statement:**  
Build a production-grade backend API for a coffee shop order management system. The API must support user authentication (with roles: customer, manager), product catalog management, order placement and tracking, payment and notification integration, idempotency for order creation, and strict order status transitions. The system should be robust, secure, and ready for deployment in a real-world environment.

**Technologies Used:**

- **Python 3.11+** — Main programming language.
- **FastAPI** — High-performance, async web framework for building APIs.
- **PostgreSQL** — Relational database for persistent storage.
- **SQLAlchemy (async)** — ORM for database access.
- **Alembic** — Database migrations.
- **Docker & Docker Compose** — Containerization and orchestration for local development and deployment.
- **Pytest** — Testing framework for unit and integration tests.
- **JWT (PyJWT)** — Authentication and role-based access control.
- **Argon2** — Secure password hashing.
- **HTTPX** — Async HTTP client for payment/notification integration.
- **Pydantic** — Data validation and serialization.

Production-grade **FastAPI** backend for the **Trio technical challenge**: order management with PostgreSQL, JWT auth (RBAC), payment and notification integration, idempotency, and strict order status flow.

## Quick start (local with Docker)

```bash
# Start Postgres and app
docker compose up --build

# Open new terminal
# Run migrations and seed catalog (one-off)
> docker compose --profile tools run --rm migrate
> docker-compose exec app python scripts/seed_catalog.py
> docker-compose exec app python scripts/seed_users.py

# API: http://localhost:8000
# Docs: http://localhost:8000/docs
```

**Default users (dev):**

- Customer: `customer@example.com` / `customer123`
- Manager: `manager@example.com` / `manager123`

## Environment variables

| Variable                          | Description                                      | Default                                                                            |
| --------------------------------- | ------------------------------------------------ | ---------------------------------------------------------------------------------- |
| `DATABASE_URL`                    | Postgres URL (async: `postgresql+asyncpg://...`) | `postgresql+asyncpg://coffee_user:coffee_pass@localhost:<port_number>/coffee_shop` |
| `JWT_SECRET_KEY`                  | Secret for signing JWTs (min 32 chars)           | _(set in production)_                                                              |
| `JWT_ALGORITHM`                   | JWT algorithm                                    | `HS256`                                                                            |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Token expiry                                     | `30`                                                                               |
| `PAYMENT_SERVICE_URL`             | Trio payment endpoint                            | `https://challenge.trio.dev/api/v1/payment`                                        |
| `NOTIFICATION_SERVICE_URL`        | Trio notification endpoint                       | `https://challenge.trio.dev/api/v1/notification`                                   |
| `APP_ENV`                         | Environment name                                 | `development`                                                                      |
| `LOG_LEVEL`                       | Logging level                                    | `INFO`                                                                             |
| `API_PREFIX`                      | API path prefix                                  | `/api/v1`                                                                          |

## Database setup (If docker not used)

1. Create DB and user:

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

Test coverage is above 90%

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

| Method | Endpoint                              | Auth     | Description                                      |
| ------ | ------------------------------------- | -------- | ------------------------------------------------ |
| GET    | `/api/v1/menu`                        | No       | Full catalog (products + variations + prices)    |
| POST   | `/api/v1/auth/token`                  | No       | Login → JWT (form: username=email, password=...) |
| POST   | `/api/v1/orders`                      | Customer | Place order (use `Idempotency-Key` header)       |
| GET    | `/api/v1/orders/{id}`                 | User     | Order details (customer: own only)               |
| PATCH  | `/api/v1/orders/{id}/status`          | Manager  | Update status (strict flow)                      |
| GET    | `/api/v1/admin/orders`                | Manager  | List all orders                                  |
| POST   | `/api/v1/admin/products`              | Manager  | Create product                                   |
| PATCH  | `/api/v1/admin/products/{product_id}` | Manager  | Update product                                   |
| DELETE | `/api/v1/admin/products/{product_id}` | Manager  | Delete product                                   |
| GET    | `/`                                   | No       | Root endpoint (API info)                         |

## Architecture

### Layered Design

The codebase is split into four layers with strict boundaries between them:

**API Layer** handles HTTP — routing, input validation via Pydantic, and auth enforcement. It delegates immediately to the service layer and has no knowledge of the database.

**Service Layer** is where all business logic lives. What happens when an order is placed? What are valid status transitions? What gets triggered on payment failure? The service layer answers all of that, coordinating between repositories and external integrations.

**Repository Layer** owns all database interaction. Services ask for data in business terms; repositories translate that into SQLAlchemy queries. This boundary is what makes the service layer independently testable — swap in a fake repository and you don't need a database to test business logic.

**External Integrations** are thin HTTP wrappers around the payment and notification providers. No business logic lives here — it's plumbing only. Keeping this strict means swapping a provider later is a one-file change.

### Project Structure

```
app/
  api/             # FastAPI routers, endpoint definitions, auth middleware
  core/            # JWT utilities, security helpers
  services/        # Business logic — one file per domain
  repositories/    # DB queries — one file per resource
  models/          # SQLAlchemy ORM models
  schemas/         # Pydantic request/response schemas
  config.py        # Environment-based configuration
  db.py            # Async DB session and engine setup
scripts/
  seed_catalog.py  # Seeds products and variations
  seed_users.py    # Seeds default customer and manager
tests/
  unit/            # Service and repository unit tests
  integration/     # Full request-cycle tests with mocked externals
```

### Database Schema

Prices are stored as integers (cents) throughout to avoid floating point issues entirely.

- **users** — email, hashed password, role. Role is a column on the user record — with two roles, a separate table adds joins with no real benefit.
- **products** — name and base price in cents.
- **product_variations** — linked to a product, name and price delta. Final price = base + delta.
- **orders** — linked to a customer, carries status enum and total in cents.
- **order_items** — line items linking an order to specific variations. Unit price is snapshotted at order time — product prices can change later and historical orders need to reflect what was actually charged.
- **payments** — one-to-one with an order. Full request and response payload stored for auditing.
- **notifications** — one row per status-change notification. Response stored for debugging and retry.
- **idempotency_keys** — SHA-256 hash of the client-provided key, linked to the resulting order and payment, with a 24-hour TTL.

Indexes on all foreign keys, the order status column, and `created_at`. Unique constraint on idempotency key hash.

### Order Status Flow

Orders move through a strict, linear sequence with no skipping and no reversals:
waiting → preparation → ready → delivered

### Idempotency

Idempotency ensures that making the same API request multiple times will not result in duplicate operations or side effects. This is especially important for payment and order creation, where network retries or client errors could otherwise create duplicate orders or charges.

**Where is idempotency used?**

- Idempotency is implemented for the `POST /api/v1/orders` endpoint (order creation).

**How does it work?**

- Clients can (optionally) include an `Idempotency-Key` header with their order creation request. This key should be a unique value generated by the client for each logical order attempt.
- On the server, the key is hashed (SHA-256) and stored in the `idempotency_keys` table, along with the resulting order and payment IDs and a TTL (typically 24 hours).
- On the first request with a new key:
  - The server processes the order and payment as normal.
  - The key and result are stored.
  - The server returns a `201 Created` response with the new order.
- On a retry with the same key (e.g., due to a network timeout or client retry):
  - The server detects the key has already been used.
  - Instead of creating a new order or charging again, it returns the original order and payment result with a `200 OK` response.
- If the key is not provided, every request is treated as a new order.

**Why is this important?**

- Prevents duplicate orders and charges if a client retries a request due to network issues or uncertainty about the previous request’s outcome.
- Makes the API safe for clients to retry requests without risk of double payment or order creation.

**Internal working:**

- The key is hashed and checked in the database before processing.
- If found, the previous result is returned.
- If not found, the order and payment are processed, and the key/result are stored for future reference.

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

## Checklist

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
- [x] Tests (unit + integration with mocked payment/notification)
- [x] Dockerfile and docker-compose (Postgres, app, migrate/seed profiles)
