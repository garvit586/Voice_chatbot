-- Documents and chunks
CREATE TABLE IF NOT EXISTS document (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kb_id       UUID NOT NULL REFERENCES knowledge_base(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    mime        TEXT NOT NULL DEFAULT 'application/pdf',
    object_key  TEXT NOT NULL,
    sha256      TEXT NOT NULL,
    pages       INT NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','ingesting','ready','error')),
    error_msg   TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS document_kb_id ON document(kb_id);

CREATE TABLE IF NOT EXISTS chunk (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    kb_id       UUID NOT NULL,
    page        INT NOT NULL DEFAULT 0,
    ordinal     INT NOT NULL,
    heading     TEXT NOT NULL DEFAULT '',
    text        TEXT NOT NULL,
    figure_key  TEXT,
    tsv         TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', heading || ' ' || text)) STORED
);
CREATE INDEX IF NOT EXISTS chunk_kb_id ON chunk(kb_id);
CREATE INDEX IF NOT EXISTS chunk_tsv ON chunk USING GIN(tsv);
CREATE INDEX IF NOT EXISTS chunk_doc ON chunk(document_id);

CREATE TABLE IF NOT EXISTS chunk_embedding (
    chunk_id    UUID NOT NULL REFERENCES chunk(id) ON DELETE CASCADE,
    model_key   TEXT NOT NULL,
    embedding   vector(2048) NOT NULL,
    PRIMARY KEY (chunk_id, model_key)
);
CREATE INDEX IF NOT EXISTS chunk_emb_model ON chunk_embedding(model_key);
