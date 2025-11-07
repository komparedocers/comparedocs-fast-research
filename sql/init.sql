-- Enable pgvector extension (if available)
-- CREATE EXTENSION IF NOT EXISTS vector;

-- Documents table
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    sha256 TEXT UNIQUE,
    filename TEXT,
    size INTEGER,
    page_count INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    status TEXT
);

-- Pages table
CREATE TABLE IF NOT EXISTS pages (
    id SERIAL PRIMARY KEY,
    doc_id TEXT REFERENCES documents(id),
    page_no INTEGER,
    status TEXT,
    s3_uri_json TEXT,
    has_text_layer BOOLEAN,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(doc_id, page_no)
);

-- Chunks table
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    doc_id TEXT REFERENCES documents(id),
    page_no INTEGER,
    order_index INTEGER,
    text TEXT,
    char_count INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Comparisons table
CREATE TABLE IF NOT EXISTS comparisons (
    id TEXT PRIMARY KEY,
    left_doc_id TEXT REFERENCES documents(id),
    right_doc_id TEXT REFERENCES documents(id),
    status TEXT,
    result JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_documents_sha256 ON documents(sha256);
CREATE INDEX IF NOT EXISTS idx_pages_doc_id ON pages(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_comparisons_status ON comparisons(status);

-- Insert test data marker
INSERT INTO documents (id, sha256, filename, size, page_count, status)
VALUES ('system-init', 'system', 'System Initialization', 0, 0, 'completed')
ON CONFLICT (id) DO NOTHING;
