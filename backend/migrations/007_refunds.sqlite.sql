CREATE TABLE refunds (
    id VARCHAR(36) PRIMARY KEY NOT NULL,
    order_id VARCHAR(36) NOT NULL UNIQUE REFERENCES orders(id),
    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    status VARCHAR(20) NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX ix_refunds_user_id ON refunds(user_id);
CREATE UNIQUE INDEX ix_orders_real_trade ON orders(provider, provider_trade_id)
WHERE provider <> 'mock' AND provider_trade_id IS NOT NULL;
