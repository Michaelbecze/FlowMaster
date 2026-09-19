# Build context is the repository root (see infra/docker-compose.yml) so this can
# install the local packages/shared dependency alongside the service's own code.
FROM python:3.11-slim
WORKDIR /app
COPY packages/shared /packages/shared
COPY services/identity/pyproject.toml .
COPY services/identity/src ./src
RUN pip install --no-cache-dir /packages/shared . uvicorn
EXPOSE 8001
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
