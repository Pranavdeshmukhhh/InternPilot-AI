# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS frontend
ARG PUBLIC_SITE_URL
ARG PUBLIC_CONTACT_EMAIL
ENV PUBLIC_SITE_URL=$PUBLIC_SITE_URL PUBLIC_CONTACT_EMAIL=$PUBLIC_CONTACT_EMAIL
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    npm ci --strict-ssl=true
COPY frontend/ ./
ENV NEXT_TELEMETRY_DISABLED=1 INTERNAL_API_URL=http://127.0.0.1:8000 PUBLIC_HTTPS=true
RUN mkdir -p /web/third-party-licenses && cd /web/node_modules && \
    find . -type f \( -iname 'license*' -o -iname 'copying*' -o -iname 'notice*' \) \
    -exec cp --parents '{}' /web/third-party-licenses/ \;
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production DATA_DIR=/data/internpilot \
    WORKER_HEARTBEAT_FILE=/tmp/internpilot-worker-heartbeat PORT=10000
WORKDIR /app
COPY backend/requirements.lock ./requirements.lock
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r requirements.lock
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    python -m playwright install --with-deps chromium && rm -rf /var/lib/apt/lists/*
RUN groupadd --gid 10001 internpilot && \
    useradd --uid 10001 --gid 10001 --create-home internpilot && \
    mkdir -p /data/internpilot && chown internpilot:internpilot /data/internpilot
COPY --from=frontend /usr/local/bin/node /usr/local/bin/node
COPY --from=frontend --chown=10001:10001 /web/.next/standalone /app/frontend
COPY --from=frontend --chown=10001:10001 /web/.next/static /app/frontend/.next/static
COPY --from=frontend --chown=10001:10001 /web/public /app/frontend/public
COPY --from=frontend /web/third-party-licenses /app/third-party-licenses
COPY --chown=10001:10001 backend/app /app/backend/app
COPY --chown=10001:10001 deploy/start.py /app/start.py
EXPOSE 10000
# Bootstrap fixes a newly mounted disk's ownership and immediately drops root.
CMD ["python", "/app/start.py"]
