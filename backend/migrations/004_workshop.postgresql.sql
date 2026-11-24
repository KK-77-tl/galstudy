ALTER TABLE users ADD COLUMN selected_character_id VARCHAR(40);

CREATE TABLE products (
	id VARCHAR(60) NOT NULL, 
	title VARCHAR(120) NOT NULL, 
	price_cents INTEGER NOT NULL, 
	currency VARCHAR(8) NOT NULL, 
	pack_spec TEXT NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE orders (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	request_id VARCHAR(36) NOT NULL, 
	product_id VARCHAR(60) NOT NULL, 
	amount_cents INTEGER NOT NULL, 
	pack_spec TEXT NOT NULL, 
	currency VARCHAR(8) NOT NULL, 
	provider VARCHAR(20) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	provider_trade_id VARCHAR(100), 
	created_at INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (user_id, request_id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(product_id) REFERENCES products (id)
);

CREATE INDEX ix_orders_user_id ON orders (user_id);

CREATE TABLE reference_images (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	data BYTEA NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	contains_real_person BOOLEAN NOT NULL, 
	rights_confirmed BOOLEAN NOT NULL, 
	person_consent_confirmed BOOLEAN NOT NULL, 
	created_at INTEGER NOT NULL, 
	expires_at INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_reference_images_user_id ON reference_images (user_id);

CREATE TABLE entitlements (
	id VARCHAR(36) NOT NULL, 
	order_id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	reservation_job_id VARCHAR(36), 
	PRIMARY KEY (id), 
	UNIQUE (order_id), 
	FOREIGN KEY(order_id) REFERENCES orders (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_entitlements_user_id ON entitlements (user_id);

CREATE TABLE payment_events (
	id VARCHAR(100) NOT NULL, 
	order_id VARCHAR(36) NOT NULL, 
	digest VARCHAR(64) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	created_at INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(order_id) REFERENCES orders (id)
);

CREATE TABLE image_jobs (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	request_id VARCHAR(36) NOT NULL, 
	entitlement_id VARCHAR(36) NOT NULL, 
	reference_id VARCHAR(36), 
	spec TEXT NOT NULL, 
	mode VARCHAR(20) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	attempts INTEGER NOT NULL, 
	remote_id VARCHAR(120), 
	error TEXT NOT NULL, 
	created_at INTEGER NOT NULL, 
	updated_at INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (user_id, request_id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(entitlement_id) REFERENCES entitlements (id), 
	FOREIGN KEY(reference_id) REFERENCES reference_images (id)
);

CREATE INDEX ix_image_jobs_user_id ON image_jobs (user_id);

CREATE TABLE characters (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	job_id VARCHAR(36) NOT NULL, 
	entitlement_id VARCHAR(36) NOT NULL, 
	name VARCHAR(40) NOT NULL, 
	persona TEXT NOT NULL, 
	address VARCHAR(40) NOT NULL, 
	mode VARCHAR(20) NOT NULL, 
	assets TEXT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	UNIQUE (job_id), 
	FOREIGN KEY(job_id) REFERENCES image_jobs (id), 
	UNIQUE (entitlement_id), 
	FOREIGN KEY(entitlement_id) REFERENCES entitlements (id)
);

CREATE INDEX ix_characters_user_id ON characters (user_id);

CREATE TABLE image_assets (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	job_id VARCHAR(36) NOT NULL, 
	data BYTEA NOT NULL, 
	slot INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (job_id, slot), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(job_id) REFERENCES image_jobs (id)
);

CREATE INDEX ix_image_assets_job_id ON image_assets (job_id);

CREATE INDEX ix_image_assets_user_id ON image_assets (user_id);
