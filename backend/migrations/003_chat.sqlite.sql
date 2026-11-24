CREATE TABLE chat_sessions (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    course_id VARCHAR(36) NOT NULL REFERENCES courses(id),
    character_id VARCHAR(40) NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    UNIQUE(user_id, course_id, character_id)
);
CREATE INDEX ix_chat_sessions_user_id ON chat_sessions(user_id);
CREATE INDEX ix_chat_sessions_course_id ON chat_sessions(course_id);
CREATE TABLE chat_messages (
    id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL REFERENCES chat_sessions(id),
    request_id VARCHAR(36) NOT NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'complete',
    mode VARCHAR(20) NOT NULL DEFAULT 'demo',
    "references" TEXT NOT NULL DEFAULT '[]',
    created_at BIGINT NOT NULL,
    UNIQUE(session_id, request_id, role)
);
CREATE INDEX ix_chat_messages_session_id ON chat_messages(session_id);
CREATE TABLE llm_usage (
    bucket VARCHAR(100) PRIMARY KEY,
    requests INTEGER NOT NULL DEFAULT 0,
    reserved_tokens INTEGER NOT NULL DEFAULT 0
);
