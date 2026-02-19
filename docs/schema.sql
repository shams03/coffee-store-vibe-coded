-- Trio Coffee Shop Order API - PostgreSQL DDL
-- Canonical schema; Alembic migrations generate from SQLAlchemy models.
-- Order status flow: waiting -> preparation -> ready -> delivered

CREATE TYPE order_status_enum AS ENUM ('waiting', 'preparation', 'ready', 'delivered');
CREATE TYPE user_role_enum AS ENUM ('customer', 'manager');

-- Users (for JWT auth; role stored here and mirrored in JWT)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    role user_role_enum NOT NULL DEFAULT 'customer',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);

-- Products (catalog)
CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    base_price_cents INTEGER NOT NULL CHECK (base_price_cents >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_products_name ON products(name);

-- Product variations (size, type, etc.) with price delta
CREATE TABLE product_variations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    price_change_cents INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(product_id, name)
);

CREATE INDEX idx_product_variations_product_id ON product_variations(product_id);

-- Idempotency keys (protect POST /orders from duplicate charges)
CREATE TABLE idempotency_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_hash VARCHAR(64) NOT NULL UNIQUE,
    key_preview VARCHAR(32),
    order_id UUID,
    payment_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX idx_idempotency_key_hash ON idempotency_keys(key_hash);
CREATE INDEX idx_idempotency_expires ON idempotency_keys(expires_at);

-- Orders
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    status order_status_enum NOT NULL DEFAULT 'waiting',
    total_cents INTEGER NOT NULL CHECK (total_cents >= 0),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_orders_customer_id ON orders(customer_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created_at ON orders(created_at DESC);

-- Order items (line items with snapshot of price at order time)
CREATE TABLE order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    variation_id UUID NOT NULL REFERENCES product_variations(id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_order_items_order_id ON order_items(order_id);

-- Payments (one per order; response stored for audit)
CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE RESTRICT UNIQUE,
    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
    request_payload JSONB,
    response_status_code INTEGER,
    response_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_payments_order_id ON payments(order_id);

-- Notifications (one row per status-change notification attempt)
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    status order_status_enum NOT NULL,
    response_status_code INTEGER,
    response_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_notifications_order_id ON notifications(order_id);

-- Sample verification queries (run after seed):
-- SELECT p.name, p.base_price_cents, v.name AS variation, v.price_change_cents
--   FROM products p
--   JOIN product_variations v ON v.product_id = p.id
--   ORDER BY p.name, v.name;
