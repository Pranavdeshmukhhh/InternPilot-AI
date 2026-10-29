-- Frozen audited v5 baseline 71ef94a; no user data.
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
	upload_approved_at VARCHAR, 
	upload_approval_digest VARCHAR(64), 
	upload_started_at VARCHAR, 
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

CREATE TABLE crawl_runs (
	id VARCHAR(36) NOT NULL, 
	owner_id VARCHAR(36) NOT NULL, 
	source_id VARCHAR(36) NOT NULL, 
	started_at VARCHAR NOT NULL, 
	finished_at VARCHAR, 
	seconds FLOAT, 
	records INTEGER NOT NULL, 
	outcome VARCHAR(30) NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE deadline_reminders (
	id VARCHAR(64) NOT NULL, 
	owner_id VARCHAR(36) NOT NULL, 
	opportunity_id VARCHAR(36) NOT NULL, 
	deadline_at VARCHAR(40) NOT NULL, 
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

CREATE TABLE gmail_connections (
	owner_id VARCHAR(36) NOT NULL, 
	email_hash VARCHAR(64) NOT NULL, 
	data_encrypted BYTEA NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	last_reserved_at VARCHAR, 
	last_sync_at VARCHAR, 
	sync_cursor INTEGER NOT NULL, 
	created_at VARCHAR NOT NULL, 
	PRIMARY KEY (owner_id), 
	UNIQUE (email_hash)
);

CREATE TABLE gmail_oauth_states (
	state_hash VARCHAR(64) NOT NULL, 
	owner_id VARCHAR(36) NOT NULL, 
	session_hash VARCHAR(64) NOT NULL, 
	verifier_encrypted BYTEA NOT NULL, 
	expires_at VARCHAR(40) NOT NULL, 
	PRIMARY KEY (state_hash)
);

CREATE TABLE host_budgets (
	host VARCHAR(253) NOT NULL, 
	next_allowed VARCHAR(40) NOT NULL, 
	PRIMARY KEY (host)
);

CREATE TABLE notification_deliveries (
	id VARCHAR(36) NOT NULL, 
	owner_id VARCHAR(36) NOT NULL, 
	notification_id VARCHAR(36) NOT NULL, 
	channel VARCHAR(20) NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	approved_at VARCHAR, 
	not_before VARCHAR, 
	attempts INTEGER NOT NULL, 
	last_error TEXT, 
	payload_encrypted BYTEA NOT NULL, 
	provider_id VARCHAR(255), 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_notification_channel UNIQUE (notification_id, channel)
);

CREATE TABLE notification_settings (
	owner_id VARCHAR(36) NOT NULL, 
	settings_encrypted BYTEA NOT NULL, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (owner_id)
);

CREATE TABLE notifications (
	id VARCHAR(36) NOT NULL, 
	owner_id VARCHAR(36) NOT NULL, 
	message TEXT NOT NULL, 
	kind VARCHAR(50) NOT NULL, 
	read BOOLEAN NOT NULL, 
	created_at VARCHAR NOT NULL, 
	opportunity_id VARCHAR(36), 
	dedupe_key VARCHAR(200), 
	PRIMARY KEY (id), 
	UNIQUE (dedupe_key)
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

CREATE TABLE outreach_contacts (
	id VARCHAR(36) NOT NULL, 
	owner_id VARCHAR(36) NOT NULL, 
	email_hash VARCHAR(64) NOT NULL, 
	data_encrypted BYTEA NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	created_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_outreach_contact UNIQUE (owner_id, email_hash)
);

CREATE TABLE outreach_messages (
	id VARCHAR(36) NOT NULL, 
	owner_id VARCHAR(36) NOT NULL, 
	contact_id VARCHAR(36) NOT NULL, 
	parent_id VARCHAR(36), 
	status VARCHAR(30) NOT NULL, 
	content_encrypted BYTEA NOT NULL, 
	approval_digest VARCHAR(64), 
	approved_at VARCHAR, 
	scheduled_at VARCHAR, 
	sending_started_at VARCHAR, 
	sent_at VARCHAR, 
	provider_id VARCHAR(255), 
	thread_id VARCHAR(255), 
	rfc_message_id VARCHAR(150) NOT NULL, 
	reason VARCHAR(500) NOT NULL, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE outreach_replies (
	id VARCHAR(36) NOT NULL, 
	owner_id VARCHAR(36) NOT NULL, 
	contact_id VARCHAR(36) NOT NULL, 
	provider_id VARCHAR(255) NOT NULL, 
	kind VARCHAR(30) NOT NULL, 
	data_encrypted BYTEA NOT NULL, 
	received_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_outreach_reply UNIQUE (owner_id, provider_id)
);

CREATE TABLE outreach_settings (
	owner_id VARCHAR(36) NOT NULL, 
	data_encrypted BYTEA NOT NULL, 
	PRIMARY KEY (owner_id)
);

CREATE TABLE saved_opportunities (
	owner_id VARCHAR(36) NOT NULL, 
	opportunity_id VARCHAR(36) NOT NULL, 
	created_at VARCHAR NOT NULL, 
	PRIMARY KEY (owner_id, opportunity_id)
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
	role VARCHAR(20) DEFAULT 'member' NOT NULL, 
	disabled BOOLEAN NOT NULL, 
	last_login_at VARCHAR(40), 
	last_seen_at VARCHAR(40), 
	created_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (email_hash)
);

CREATE TABLE worker_heartbeats (
	id VARCHAR(100) NOT NULL, 
	last_seen VARCHAR NOT NULL, 
	concurrency INTEGER NOT NULL, 
	stopped BOOLEAN NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_applications_opportunity_id ON applications (opportunity_id);

CREATE INDEX ix_applications_owner_id ON applications (owner_id);

CREATE INDEX ix_applications_status ON applications (status);

CREATE INDEX ix_audit_events_created_at ON audit_events (created_at);

CREATE INDEX ix_audit_events_owner_id ON audit_events (owner_id);

CREATE INDEX ix_crawl_runs_owner_id ON crawl_runs (owner_id);

CREATE INDEX ix_crawl_runs_source_id ON crawl_runs (source_id);

CREATE INDEX ix_crawl_runs_started_at ON crawl_runs (started_at);

CREATE INDEX ix_deadline_reminders_owner_id ON deadline_reminders (owner_id);

CREATE INDEX ix_documents_owner_id ON documents (owner_id);

CREATE INDEX ix_gmail_oauth_states_owner_id ON gmail_oauth_states (owner_id);

CREATE INDEX ix_notification_deliveries_notification_id ON notification_deliveries (notification_id);

CREATE INDEX ix_notification_deliveries_owner_id ON notification_deliveries (owner_id);

CREATE INDEX ix_notifications_owner_id ON notifications (owner_id);

CREATE INDEX ix_opportunities_first_discovered ON opportunities (first_discovered);

CREATE INDEX ix_outreach_contacts_owner_id ON outreach_contacts (owner_id);

CREATE INDEX ix_outreach_messages_contact_id ON outreach_messages (contact_id);

CREATE INDEX ix_outreach_messages_owner_id ON outreach_messages (owner_id);

CREATE INDEX ix_outreach_messages_scheduled_at ON outreach_messages (scheduled_at);

CREATE INDEX ix_outreach_messages_status ON outreach_messages (status);

CREATE INDEX ix_outreach_replies_contact_id ON outreach_replies (contact_id);

CREATE INDEX ix_outreach_replies_owner_id ON outreach_replies (owner_id);

CREATE INDEX ix_sessions_user_id ON sessions (user_id);

CREATE INDEX ix_sources_owner_id ON sources (owner_id);

CREATE INDEX ix_task_claim ON tasks (status, available_at, priority);

CREATE INDEX ix_tasks_owner_id ON tasks (owner_id);

CREATE INDEX ix_tasks_status ON tasks (status);

CREATE INDEX ix_worker_heartbeats_last_seen ON worker_heartbeats (last_seen);
