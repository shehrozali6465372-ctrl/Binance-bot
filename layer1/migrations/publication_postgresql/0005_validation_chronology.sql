-- Add a monotonic chronology key for new validation records.
-- Existing rows intentionally remain NULL: historical insertion order cannot
-- be reconstructed safely from content hashes, timestamps, or physical row IDs.
CREATE SEQUENCE IF NOT EXISTS content_draft_validation_sequence_seq;
ALTER TABLE content_draft_validation_results
    ADD COLUMN IF NOT EXISTS validation_sequence BIGINT;
ALTER TABLE content_draft_validation_results
    ALTER COLUMN validation_sequence SET DEFAULT nextval('content_draft_validation_sequence_seq');
ALTER SEQUENCE content_draft_validation_sequence_seq
    OWNED BY content_draft_validation_results.validation_sequence;
CREATE UNIQUE INDEX IF NOT EXISTS idx_content_draft_validation_sequence
    ON content_draft_validation_results(validation_sequence)
    WHERE validation_sequence IS NOT NULL;

CREATE SEQUENCE IF NOT EXISTS visual_validation_sequence_seq;
ALTER TABLE visual_validation_results
    ADD COLUMN IF NOT EXISTS validation_sequence BIGINT;
ALTER TABLE visual_validation_results
    ALTER COLUMN validation_sequence SET DEFAULT nextval('visual_validation_sequence_seq');
ALTER SEQUENCE visual_validation_sequence_seq
    OWNED BY visual_validation_results.validation_sequence;
CREATE UNIQUE INDEX IF NOT EXISTS idx_visual_validation_sequence
    ON visual_validation_results(validation_sequence)
    WHERE validation_sequence IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_content_draft_validation_chronology
    ON content_draft_validation_results(draft_hash,created_at DESC,validation_sequence DESC);
CREATE INDEX IF NOT EXISTS idx_visual_validation_chronology
    ON visual_validation_results(draft_hash,image_hash,created_at DESC,validation_sequence DESC);
