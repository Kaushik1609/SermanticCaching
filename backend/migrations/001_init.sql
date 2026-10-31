CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE cache_entries (
  id                BIGSERIAL PRIMARY KEY,
  context_key       TEXT        NOT NULL DEFAULT 'default',
  query_text        TEXT        NOT NULL,
  exact_key         CHAR(64)    NOT NULL,
  query_embedding   VECTOR(384) NOT NULL,
  response_text     TEXT        NOT NULL,
  embedding_model   TEXT        NOT NULL,
  config_hash       CHAR(64)    NOT NULL,
  prompt_tokens     INT,
  completion_tokens INT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at        TIMESTAMPTZ,
  hit_count         INT         NOT NULL DEFAULT 0,
  status            TEXT        NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INVALIDATED'))
);
CREATE UNIQUE INDEX uq_exact_active ON cache_entries (exact_key) WHERE status = 'ACTIVE';
CREATE INDEX idx_ctx_status ON cache_entries (context_key, status);
CREATE INDEX idx_embedding_hnsw ON cache_entries USING hnsw (query_embedding vector_cosine_ops);

CREATE TABLE query_log (
  id             BIGSERIAL PRIMARY KEY,
  ts             TIMESTAMPTZ NOT NULL DEFAULT now(),
  context_key    TEXT NOT NULL,
  strategy       TEXT NOT NULL,
  outcome        TEXT NOT NULL,
  reason_code    TEXT NOT NULL,
  similarity     REAL,
  lookup_ms      REAL,
  total_ms       REAL,
  llm_called     BOOLEAN NOT NULL,
  prompt_tokens  INT,
  completion_tokens INT,
  matched_entry_id BIGINT
);
