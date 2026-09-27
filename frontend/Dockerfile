FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=$BACKEND_URL NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN adduser -D -u 10001 argus
COPY --from=build --chown=argus /app/.next/standalone ./
COPY --from=build --chown=argus /app/.next/static ./.next/static
# Standalone output does not include public/ (country outlines, icons).
COPY --from=build --chown=argus /app/public ./public
USER argus
EXPOSE 3000
CMD ["node", "server.js"]
