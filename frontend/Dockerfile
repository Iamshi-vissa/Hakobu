# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22-alpine AS builder
WORKDIR /app
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S hakobu && adduser -S hakobu -G hakobu
COPY --from=builder --chown=hakobu:hakobu /app/.next/standalone ./
COPY --from=builder --chown=hakobu:hakobu /app/.next/static ./.next/static
COPY --from=builder --chown=hakobu:hakobu /app/public ./public
USER hakobu
EXPOSE 3000
CMD ["node", "server.js"]
