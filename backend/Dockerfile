# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    DATA_DIR=/data
WORKDIR /app
COPY requirements.txt ./
# Optional corporate/session CA: docker build --secret id=proxy_ca,src=<bundle>.
# The mounted CA is not copied into the image. Normal desktop builds need none.
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r requirements.txt
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    python -m playwright install --with-deps chromium && \
    rm -rf /var/lib/apt/lists/*
RUN groupadd --gid 10001 internpilot && \
    useradd --uid 10001 --gid 10001 --create-home internpilot && \
    mkdir -p /data && chown internpilot:internpilot /data && chmod 700 /data
COPY --chown=internpilot:internpilot . .
USER internpilot
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
