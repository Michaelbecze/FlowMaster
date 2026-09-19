import os

os.environ.setdefault("KAFKA_BROKERS", "localhost:9092")
os.environ.setdefault("CLICKHOUSE_URL", "http://localhost:8123")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
