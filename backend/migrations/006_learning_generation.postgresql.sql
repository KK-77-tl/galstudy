ALTER TABLE courses ADD COLUMN story_token VARCHAR(36);
ALTER TABLE source_files ADD COLUMN draft_mode VARCHAR(20) NOT NULL DEFAULT 'demo';
ALTER TABLE source_files ADD COLUMN processing_token VARCHAR(36);
ALTER TABLE knowledge_points ADD COLUMN kind VARCHAR(20) NOT NULL DEFAULT 'excerpt';
ALTER TABLE knowledge_points ADD COLUMN mode VARCHAR(20) NOT NULL DEFAULT 'demo';
ALTER TABLE knowledge_points ADD COLUMN quote TEXT NOT NULL DEFAULT '';
UPDATE knowledge_points SET mode = 'manual', kind = 'concept' WHERE chunk_id IS NULL;
