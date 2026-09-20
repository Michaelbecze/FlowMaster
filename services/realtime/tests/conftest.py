import os

os.environ.setdefault("KAFKA_BROKERS", "localhost:9092")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("IDENTITY_BASE_URL", "http://localhost:8001")
