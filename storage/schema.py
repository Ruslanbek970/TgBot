from __future__ import annotations

try:
    from .db import get_cursor, is_available
except ImportError:
    from db import get_cursor, is_available


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS storage_companies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS storage_documents (
    id UUID PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES storage_companies(id) ON DELETE CASCADE,
    original_name VARCHAR(255) NOT NULL,
    secure_path VARCHAR(500) NOT NULL,
    file_size BIGINT NOT NULL DEFAULT 0,
    min_role VARCHAR(20) NOT NULL DEFAULT 'employee',
    search_text TEXT NOT NULL DEFAULT '',
    search_vector TSVECTOR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS storage_documents_search_idx
    ON storage_documents USING GIN(search_vector);

CREATE TABLE IF NOT EXISTS storage_users (
    telegram_id BIGINT PRIMARY KEY,
    username VARCHAR(100),
    role VARCHAR(20) NOT NULL DEFAULT 'employee',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS storage_access_logs (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT,
    document_id UUID REFERENCES storage_documents(id) ON DELETE SET NULL,
    action_type VARCHAR(50) NOT NULL,
    allowed BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def init_schema() -> bool:
    if not is_available():
        return False
    with get_cursor() as cursor:
        cursor.execute(SCHEMA_SQL)
    return True
