import os

os.environ.setdefault("CLICKHOUSE_URL", "http://localhost:8123")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("IDENTITY_BASE_URL", "http://localhost:8001")
