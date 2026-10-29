# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    npm ci --strict-ssl=true

FROM dependencies AS build
ARG PUBLIC_SITE_URL
ARG PUBLIC_CONTACT_EMAIL
ENV PUBLIC_SITE_URL=$PUBLIC_SITE_URL PUBLIC_CONTACT_EMAIL=$PUBLIC_CONTACT_EMAIL
ARG INTERNAL_API_URL=http://backend:8000
ENV INTERNAL_API_URL=$INTERNAL_API_URL NEXT_TELEMETRY_DISABLED=1
COPY . .
RUN mkdir -p /app/third-party-licenses && cd /app/node_modules && \
    find . -type f \( -iname 'license*' -o -iname 'copying*' -o -iname 'notice*' \) \
    -exec cp --parents '{}' /app/third-party-licenses/ \;
RUN npm run build

FROM node:22-bookworm-slim AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /app
RUN groupadd --gid 10001 internpilot && useradd --uid 10001 --gid 10001 internpilot
COPY --from=build --chown=internpilot:internpilot /app/.next/standalone ./
COPY --from=build --chown=internpilot:internpilot /app/.next/static ./.next/static
COPY --from=build --chown=internpilot:internpilot /app/public ./public
COPY --from=build /app/third-party-licenses /app/third-party-licenses
USER internpilot
EXPOSE 3000
CMD ["node", "server.js"]
