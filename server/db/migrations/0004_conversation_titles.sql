-- Backfill titles from each conversation's first question.
UPDATE conversation c
SET title = left(regexp_replace(m.text, '\s+', ' ', 'g'), 80)
FROM (
    SELECT DISTINCT ON (conversation_id) conversation_id, text
    FROM message
    WHERE role = 'user'
    ORDER BY conversation_id, created_at
) m
WHERE m.conversation_id = c.id AND c.title = '';

CREATE INDEX IF NOT EXISTS conversation_last_at ON conversation(last_at DESC);
