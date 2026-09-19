# Build context is the repository root (see infra/docker-compose.yml).
FROM python:3.11-slim
WORKDIR /app
COPY packages/shared /packages/shared
COPY services/query-api/pyproject.toml .
COPY services/query-api/src ./src
RUN pip install --no-cache-dir /packages/shared . uvicorn
EXPOSE 8005
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8005"]
