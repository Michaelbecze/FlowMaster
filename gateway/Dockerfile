# Build context is the repository root (see infra/docker-compose.yml).
FROM python:3.11-slim
WORKDIR /app
COPY packages/shared /packages/shared
COPY gateway/pyproject.toml .
COPY gateway/src ./src
RUN pip install --no-cache-dir /packages/shared . uvicorn
EXPOSE 8080
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
