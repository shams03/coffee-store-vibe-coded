# Coffee Shop API – Full Setup & Postman Testing Guide

Use this on a new laptop to go from zero to full API verification: DB seed → run app → test every endpoint in Postman.

---

## 1. Prerequisites

- Python 3.9+ with venv
- PostgreSQL (or Docker for Postgres)
- Postman (or any HTTP client)

---

## 2. Seed & Run (step-by-step)

### 2.1 Start Postgres (Docker)

```bash
cd /path/to/test-19feb
docker compose up -d db
```

Wait ~5 seconds, then:

```bash
docker compose exec db psql -U coffee_user -d coffee_shop -c "SELECT 1"
# Should print ?column? 1
```

### 2.2 Create virtualenv and install

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install python-multipart argon2-cffi
```

### 2.3 Set environment and run migrations

```bash
export DATABASE_URL="postgresql+asyncpg://coffee_user:coffee_pass@localhost:5432/coffee_shop"
export JWT_SECRET_KEY="your-secret-key-at-least-32-characters-long"

alembic upgrade head
```

### 2.4 Seed database (catalog + users)

```bash
# Same DATABASE_URL as above
python -m scripts.seed_catalog
python -m scripts.seed_users
```

You should see:
- `Catalog seeded successfully.`
- `Users seeded (customer@example.com, manager@example.com).`

### 2.5 Start the API

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Base URL for Postman: **`http://localhost:8000`**

---

## 3. Get IDs for ordering (required for POST /orders)

Before creating orders you need **product_id** and **variation_id** from the menu.

1. In Postman: **GET** `http://localhost:8000/api/v1/menu` (no auth).
2. From the response, copy one product’s `id` and one of its variations’ `id`.  
   Example: Latte `id` + variation "Medium" `id`.

Use these in the **Body** of **POST /api/v1/orders** below.

---

## 4. Postman: All APIs (headers, body, auth)

### 4.1 No auth

| # | Method | URL | Headers | Body | Notes |
|---|--------|-----|---------|------|--------|
| 1 | GET | `http://localhost:8000/health` | *(none)* | - | 200, `{"status":"ok"}` |
| 2 | GET | `http://localhost:8000/metrics` | *(none)* | - | 200, Prometheus text |
| 3 | GET | `http://localhost:8000/api/v1/menu` | *(none)* | - | 200, list of products with variations |

---

### 4.2 Auth – get tokens

**POST** `http://localhost:8000/api/v1/auth/token`

- **Headers**
  - `Content-Type`: `application/x-www-form-urlencoded`
- **Body** (x-www-form-urlencoded)
  - `username`: `customer@example.com`
  - `password`: `customer123`

**Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

Save `access_token` as **Customer Token** (e.g. Postman environment variable `customer_token`).

Repeat with manager:

- **Body**
  - `username`: `manager@example.com`
  - `password`: `manager123`

Save that token as **Manager Token** (e.g. `manager_token`).

---

### 4.3 Orders (customer: create order; both: get order)

**POST** `http://localhost:8000/api/v1/orders` — *Customer only*

- **Headers**
  - `Content-Type`: `application/json`
  - `Authorization`: `Bearer {{customer_token}}`
  - `Idempotency-Key`: `order-001` *(optional but recommended; use unique value per logical order)*
- **Body** (raw JSON)

Replace `PRODUCT_UUID` and `VARIATION_UUID` with real IDs from **GET /api/v1/menu** (e.g. one Latte product id and one Latte variation id).

```json
{
  "items": [
    {
      "product_id": "PRODUCT_UUID",
      "variation_id": "VARIATION_UUID",
      "quantity": 1
    }
  ],
  "metadata": {},
  "total_cents": null
}
```

- `total_cents`: optional. If you send it, it must match server-computed total or you get **409**.
- **Expected:** **201** (new order) or **200** (replay with same `Idempotency-Key`).  
  **402** if payment fails. **409** if total mismatch.

Copy `id` from the response for the next request (Get order).

---

**GET** `http://localhost:8000/api/v1/orders/{{order_id}}` — *Customer: own orders only; Manager: any*

- **Headers**
  - `Authorization`: `Bearer {{customer_token}}` or `Bearer {{manager_token}}`
- **Path**
  - `order_id`: UUID of the order (e.g. from POST /orders response)
- **Body:** none

**Expected:** 200 with order details. 404 if not found or customer not owner.

---

### 4.4 Order status (manager only)

**PATCH** `http://localhost:8000/api/v1/orders/{{order_id}}/status`

- **Headers**
  - `Content-Type`: `application/json`
  - `Authorization`: `Bearer {{manager_token}}`
- **Path**
  - `order_id`: UUID of the order
- **Body** (raw JSON)

```json
{
  "status": "preparation"
}
```

Allowed values in order: `waiting` → `preparation` → `ready` → `delivered`.  
Send the **next** status only (e.g. from `waiting` send `preparation`).

**Expected:** 200 with updated order. 400 if invalid transition. 404 if order not found.

---

### 4.5 Admin – products (manager only)

**POST** `http://localhost:8000/api/v1/admin/products` — Create product

- **Headers**
  - `Content-Type`: `application/json`
  - `Authorization`: `Bearer {{manager_token}}`
- **Body** (raw JSON)

```json
{
  "name": "Mocha",
  "base_price_cents": 500,
  "variations": [
    { "name": "Small", "price_change_cents": 0 },
    { "name": "Large", "price_change_cents": 80 }
  ]
}
```

**Expected:** 201 with created product (id, name, base_price_cents, variations).

---

**PATCH** `http://localhost:8000/api/v1/admin/products/{{product_id}}` — Update product

- **Headers**
  - `Content-Type`: `application/json`
  - `Authorization`: `Bearer {{manager_token}}`
- **Path**
  - `product_id`: UUID of the product
- **Body** (raw JSON, all fields optional)

```json
{
  "name": "Mocha Updated",
  "base_price_cents": 550
}
```

**Expected:** 200 with updated product. 404 if product not found.

---

**DELETE** `http://localhost:8000/api/v1/admin/products/{{product_id}}` — Delete product

- **Headers**
  - `Authorization`: `Bearer {{manager_token}}`
- **Path**
  - `product_id`: UUID of the product
- **Body:** none

**Expected:** 204 No Content. 404 if product not found.

---

## 5. Quick reference table

| Method | Endpoint | Auth | Headers | Body |
|--------|----------|------|---------|------|
| GET | `/health` | No | - | - |
| GET | `/metrics` | No | - | - |
| GET | `/api/v1/menu` | No | - | - |
| POST | `/api/v1/auth/token` | No | Content-Type: application/x-www-form-urlencoded | username, password (form) |
| POST | `/api/v1/orders` | Customer | Authorization: Bearer \<token\>, optional Idempotency-Key, Content-Type: application/json | items[], metadata?, total_cents? |
| GET | `/api/v1/orders/{order_id}` | Customer/Manager | Authorization: Bearer \<token\> | - |
| PATCH | `/api/v1/orders/{order_id}/status` | Manager | Authorization: Bearer \<token\>, Content-Type: application/json | {"status": "preparation"\|"ready"\|"delivered"} |
| POST | `/api/v1/admin/products` | Manager | Authorization: Bearer \<token\>, Content-Type: application/json | name, base_price_cents, variations[] |
| PATCH | `/api/v1/admin/products/{product_id}` | Manager | Authorization: Bearer \<token\>, Content-Type: application/json | name?, base_price_cents? |
| DELETE | `/api/v1/admin/products/{product_id}` | Manager | Authorization: Bearer \<token\> | - |

---

## 6. Suggested Postman flow

1. **GET /health** → check server is up.
2. **GET /api/v1/menu** → copy one `product_id` and one `variation_id` (same product).
3. **POST /api/v1/auth/token** (customer) → save `access_token` as `customer_token`.
4. **POST /api/v1/auth/token** (manager) → save `access_token` as `manager_token`.
5. **POST /api/v1/orders** with customer token and the ids from step 2; optional `Idempotency-Key: test-1` → save returned `id` as `order_id`.
6. **GET /api/v1/orders/{{order_id}}** with customer token → 200.
7. **PATCH /api/v1/orders/{{order_id}}/status** with manager token, body `{"status":"preparation"}` → then `"ready"` → then `"delivered"`.
8. **POST /api/v1/admin/products** with manager token → 201.
9. **PATCH** and **DELETE** that product with manager token.

---

## 7. Seed commands (copy-paste)

```bash
# 1) Start DB
docker compose up -d db
sleep 5

# 2) Env
export DATABASE_URL="postgresql+asyncpg://coffee_user:coffee_pass@localhost:5432/coffee_shop"
export JWT_SECRET_KEY="your-secret-key-at-least-32-characters-long"

# 3) Migrate
alembic upgrade head

# 4) Seed
python -m scripts.seed_catalog
python -m scripts.seed_users

# 5) Run API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Default users:

- **Customer:** `customer@example.com` / `customer123`
- **Manager:** `manager@example.com` / `manager123`
