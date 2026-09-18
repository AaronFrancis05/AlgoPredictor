# AlgoPredict web (Next.js standalone server).
#   docker build -t algopredict-web \
#     --build-arg API_INTERNAL_URL=http://api:8000 \
#     --build-arg NEXT_PUBLIC_SITE_URL=https://algopredict.example apps/web
#   docker run --env-file apps/web/.env -p 3000:3000 algopredict-web
# API_INTERNAL_URL and NEXT_PUBLIC_SITE_URL are fixed at BUILD time: the /api/v1 rewrite target is written into
# .next/routes-manifest.json and NEXT_PUBLIC_* is inlined into the browser bundle. Rebuild to change them.
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22-alpine AS build
WORKDIR /app
ARG API_INTERNAL_URL=http://api:8000
ARG NEXT_PUBLIC_SITE_URL=http://localhost:3000
ENV API_INTERNAL_URL=$API_INTERNAL_URL NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ARG API_INTERNAL_URL=http://api:8000
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0 API_INTERNAL_URL=$API_INTERNAL_URL
RUN addgroup -S -g 10001 app && adduser -S -u 10001 -G app app
COPY --from=build --chown=app:app /app/.next/standalone ./
COPY --from=build --chown=app:app /app/.next/static ./.next/static
COPY --from=build --chown=app:app /app/public ./public
USER app
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3000/robots.txt >/dev/null || exit 1
# Runtime env (not baked): PROXY_SHARED_SECRET, WEB_TRUSTED_PROXY_COUNT, REVALIDATE_SECRET
CMD ["node", "server.js"]
