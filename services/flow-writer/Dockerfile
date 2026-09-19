# Build context is the repository root (see infra/docker-compose.yml).
FROM python:3.11-slim
WORKDIR /app
COPY packages/shared /packages/shared
COPY services/flow-writer/pyproject.toml .
COPY services/flow-writer/src ./src
COPY services/flow-writer/migrations ./migrations
RUN pip install --no-cache-dir /packages/shared . uvicorn
EXPOSE 8003
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8003"]
