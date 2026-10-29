-- Frozen original v1 schema 822610b - synthetic tests only
CREATE TABLE applications (
	id VARCHAR(36) NOT NULL, 
	owner_id VARCHAR(36) NOT NULL, 
	opportunity_id VARCHAR(36) NOT NULL, 
	status VARCHAR(40) NOT NULL, 
	reason TEXT NOT NULL, 
	document_id VARCHAR(36), 
	screenshot_id VARCHAR(36), 
	confirmation_id VARCHAR(200), 
	confirmation_encrypted BYTEA, 
	snapshot_encrypted BYTEA, 
	session_encrypted BYTEA, 
	approved_at VARCHAR, 
	approval_digest VARCHAR(64), 
	submission_started_at VARCHAR, 
	is_demo BOOLEAN NOT NULL, 
	preparation_seconds FLOAT, 
	submission_seconds FLOAT, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_candidate_opportunity UNIQUE (owner_id, opportunity_id)
);

CREATE TABLE audit_events (
	id VARCHAR(36) NOT NULL, 
	owner_id VARCHAR(36) NOT NULL, 
	kind VARCHAR(80) NOT NULL, 
	message TEXT NOT NULL, 
	application_id VARCHAR(36), 
	created_at VARCHAR NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE documents (
	id VARCHAR(36) NOT NULL, 
	owner_id VARCHAR(36) NOT NULL, 
	opportunity_id VARCHAR(36), 
	filename VARCHAR(250) NOT NULL, 
	kind VARCHAR(30) NOT NULL, 
	version INTEGER NOT NULL, 
	content_encrypted BYTEA NOT NULL, 
	metadata_encrypted BYTEA NOT NULL, 
	created_at VARCHAR NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE notifications (
	id VARCHAR(36) NOT NULL, 
	owner_id VARCHAR(36) NOT NULL, 
	message TEXT NOT NULL, 
	kind VARCHAR(50) NOT NULL, 
	read BOOLEAN NOT NULL, 
	created_at VARCHAR NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE opportunities (
	id VARCHAR(36) NOT NULL, 
	fingerprint VARCHAR(64) NOT NULL, 
	data JSON NOT NULL, 
	first_discovered VARCHAR NOT NULL, 
	last_verified VARCHAR NOT NULL, 
	discovery_latency_seconds FLOAT, 
	PRIMARY KEY (id), 
	UNIQUE (fingerprint)
);

CREATE TABLE schema_versions (
	version SERIAL NOT NULL, 
	applied_at VARCHAR NOT NULL, 
	PRIMARY KEY (version)
);

CREATE TABLE sessions (
	token_hash VARCHAR(64) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	csrf_token VARCHAR(100) NOT NULL, 
	expires_at VARCHAR(40) NOT NULL, 
	PRIMARY KEY (token_hash)
);

CREATE TABLE source_opportunities (
	source_id VARCHAR(36) NOT NULL, 
	opportunity_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (source_id, opportunity_id)
);

CREATE TABLE sources (
	id VARCHAR(36) NOT NULL, 
	owner_id VARCHAR(36) NOT NULL, 
	kind VARCHAR(40) NOT NULL, 
	slug VARCHAR(200) NOT NULL, 
	company VARCHAR(200) NOT NULL, 
	url TEXT, 
	permitted BOOLEAN NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	interval_seconds INTEGER NOT NULL, 
	last_attempt VARCHAR, 
	last_success VARCHAR, 
	next_run VARCHAR, 
	status VARCHAR NOT NULL, 
	error TEXT, 
	failures INTEGER NOT NULL, 
	cache JSON NOT NULL, 
	discovered_count INTEGER NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE tasks (
	id VARCHAR(36) NOT NULL, 
	owner_id VARCHAR(36) NOT NULL, 
	kind VARCHAR(30) NOT NULL, 
	dedupe_key VARCHAR(150) NOT NULL, 
	payload JSON NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	priority INTEGER NOT NULL, 
	attempts INTEGER NOT NULL, 
	lease_owner VARCHAR(100), 
	lease_until VARCHAR, 
	available_at VARCHAR NOT NULL, 
	error TEXT, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (dedupe_key)
);

CREATE TABLE users (
	id VARCHAR(36) NOT NULL, 
	email_hash VARCHAR(64) NOT NULL, 
	email_encrypted BYTEA NOT NULL, 
	password_hash TEXT NOT NULL, 
	profile_encrypted BYTEA NOT NULL, 
	policy_encrypted BYTEA NOT NULL, 
	created_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (email_hash)
);

CREATE INDEX ix_applications_opportunity_id ON applications (opportunity_id);

CREATE INDEX ix_applications_owner_id ON applications (owner_id);

CREATE INDEX ix_applications_status ON applications (status);

CREATE INDEX ix_audit_events_created_at ON audit_events (created_at);

CREATE INDEX ix_audit_events_owner_id ON audit_events (owner_id);

CREATE INDEX ix_documents_owner_id ON documents (owner_id);

CREATE INDEX ix_notifications_owner_id ON notifications (owner_id);

CREATE INDEX ix_opportunities_first_discovered ON opportunities (first_discovered);

CREATE INDEX ix_sessions_user_id ON sessions (user_id);

CREATE INDEX ix_sources_owner_id ON sources (owner_id);

CREATE INDEX ix_task_claim ON tasks (status, available_at, priority);

CREATE INDEX ix_tasks_owner_id ON tasks (owner_id);

CREATE INDEX ix_tasks_status ON tasks (status);
