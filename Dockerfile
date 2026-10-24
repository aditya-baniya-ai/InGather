# One image: builds the React app, then serves it and the API from FastAPI on :8000.
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_SYSTEM_PYTHON=1
RUN pip install --no-cache-dir uv
WORKDIR /app/backend
COPY backend/pyproject.toml ./
RUN uv pip install --no-cache -r pyproject.toml
COPY backend/ ./
COPY --from=web /web/dist /app/frontend/dist
ENV STATIC_DIR=/app/frontend/dist MEDIA_DIR=/app/media
RUN useradd -m app && mkdir -p /app/media && chown app /app/media
USER app
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && if [ \"$DEMO_MODE\" = \"true\" ]; then python -m app.seed; fi && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
