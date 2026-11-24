CREATE TABLE IF NOT EXISTS users (
	id VARCHAR(36) NOT NULL, 
	email VARCHAR(254) NOT NULL, 
	password TEXT NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (email)
);

CREATE TABLE IF NOT EXISTS courses (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	title VARCHAR(120) NOT NULL, 
	demo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS ix_courses_user_id ON courses (user_id);

CREATE TABLE IF NOT EXISTS sessions (
	token VARCHAR(64) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	expires INTEGER NOT NULL, 
	PRIMARY KEY (token), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS attempts (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	course_id VARCHAR(36) NOT NULL, 
	question TEXT NOT NULL, 
	answer TEXT NOT NULL, 
	correct BOOLEAN NOT NULL, 
	explanation TEXT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(course_id) REFERENCES courses (id)
);

CREATE TABLE IF NOT EXISTS saves (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	course_id VARCHAR(36) NOT NULL, 
	node VARCHAR(60) NOT NULL, 
	score INTEGER NOT NULL, 
	version INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (user_id, course_id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(course_id) REFERENCES courses (id)
);

CREATE TABLE IF NOT EXISTS source_files (
	id VARCHAR(36) NOT NULL, 
	course_id VARCHAR(36) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	data BYTEA NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	error TEXT NOT NULL, 
	attempts INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(course_id) REFERENCES courses (id)
);

CREATE INDEX IF NOT EXISTS ix_source_files_course_id ON source_files (course_id);

CREATE TABLE IF NOT EXISTS source_chunks (
	id VARCHAR(36) NOT NULL, 
	file_id VARCHAR(36) NOT NULL, 
	location VARCHAR(120) NOT NULL, 
	text TEXT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(file_id) REFERENCES source_files (id)
);

CREATE INDEX IF NOT EXISTS ix_source_chunks_file_id ON source_chunks (file_id);

CREATE TABLE IF NOT EXISTS knowledge_points (
	id VARCHAR(36) NOT NULL, 
	course_id VARCHAR(36) NOT NULL, 
	chunk_id VARCHAR(36), 
	text TEXT NOT NULL, 
	confirmed BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(course_id) REFERENCES courses (id), 
	FOREIGN KEY(chunk_id) REFERENCES source_chunks (id)
);

CREATE INDEX IF NOT EXISTS ix_knowledge_points_course_id ON knowledge_points (course_id);
