CREATE TABLE stories (
    id VARCHAR(36) PRIMARY KEY,
    course_id VARCHAR(36) NOT NULL REFERENCES courses(id),
    revision INTEGER NOT NULL,
    graph TEXT NOT NULL,
    mode VARCHAR(30) NOT NULL,
    UNIQUE(course_id, revision)
);
CREATE INDEX ix_stories_course_id ON stories(course_id);
ALTER TABLE saves ADD COLUMN story_id VARCHAR(36) REFERENCES stories(id);
ALTER TABLE attempts ADD COLUMN story_id VARCHAR(36) REFERENCES stories(id);
ALTER TABLE attempts ADD COLUMN node_id VARCHAR(60);
ALTER TABLE attempts ADD COLUMN correct_answer TEXT NOT NULL DEFAULT '';
ALTER TABLE attempts ADD COLUMN reviewed BOOLEAN NOT NULL DEFAULT FALSE;
