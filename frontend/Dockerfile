# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install -g pnpm
RUN pnpm install 
COPY . .
ARG VITE_API_URL=http://localhost:8000
ARG VITE_SUPERSET_URL=http://localhost:8088
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_SUPERSET_URL=$VITE_SUPERSET_URL
RUN npm run build

# ── Stage 2: serve ────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
