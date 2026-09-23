FROM python:3.13-slim@sha256:8d9d0b8bcf6506481eae4907c18f5e3e7902e629f5f6d684f9e7c32e85e3ddf0
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 NEXA_VERSION_FILE=/app/VERSION
WORKDIR /app
COPY backend/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home nexa
COPY backend /app/backend
COPY VERSION /app/VERSION
RUN pip install --no-cache-dir --no-deps /app/backend
WORKDIR /app/backend
USER 10001:10001
CMD ["uvicorn", "nexa.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--proxy-headers", "--forwarded-allow-ips", "*"]
