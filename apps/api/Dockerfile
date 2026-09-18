# AlgoPredict API (FastAPI) - also used for the arq worker and migrations:
#   docker build -t algopredict-api apps/api
#   docker run --env-file apps/api/.env -p 8000:8000 algopredict-api                               # API
#   docker run --env-file apps/api/.env algopredict-api arq app.workers.worker.WorkerSettings       # worker
#   docker run --env-file apps/api/.env algopredict-api alembic upgrade head                        # migrations
FROM python:3.11-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY pyproject.toml ./
COPY app ./app
RUN python -m venv /venv && /venv/bin/pip install .

FROM python:3.11-slim
ENV PATH=/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 ENVIRONMENT=production
RUN useradd --system --uid 10001 --home /app app
WORKDIR /app
COPY --from=build /venv /venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
USER app
EXPOSE 8000
# No Docker HEALTHCHECK: the same image runs the arq worker, which has no HTTP port. Configure the health check
# on the platform for the API service only (GET /healthz on port 8000).
# --no-proxy-headers: uvicorn must not rewrite the client address from X-Forwarded-For (clients can forge it);
# the app decides whom to trust (X-Client-IP + PROXY_SHARED_SECRET, or TRUSTED_PROXY_COUNT).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--workers", "2"]
