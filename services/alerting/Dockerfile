# Build context is the repository root (see infra/docker-compose.yml).
# Placeholder service (/healthz only) until User Story 4 is implemented.
FROM python:3.11-slim
WORKDIR /app
COPY packages/shared /packages/shared
COPY services/alerting/pyproject.toml .
COPY services/alerting/src ./src
RUN pip install --no-cache-dir /packages/shared fastapi uvicorn[standard]
EXPOSE 8006
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8006"]
