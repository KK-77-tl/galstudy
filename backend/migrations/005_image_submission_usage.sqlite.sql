CREATE TABLE image_submission_usage (
    bucket VARCHAR(100) PRIMARY KEY NOT NULL,
    submissions INTEGER NOT NULL DEFAULT 0
);
