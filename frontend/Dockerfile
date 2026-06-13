# ── Stage 1: Build ────────────────────────────────────────────────────────────
# node:18-slim (Debian, NOT Alpine) avoids musl/glibc issues that cause
# npm install and Vite's esbuild binary to hang or fail silently on Alpine.
FROM node:18-slim AS builder

WORKDIR /app

# Copy lockfile + manifest together — npm ci uses exact locked versions,
# never resolves the registry, and exits fast on any mismatch.
COPY package.json package-lock.json ./
RUN npm ci --prefer-offline

# Vite requires index.html at project root
COPY index.html      ./
COPY vite.config.js  ./
COPY src             ./src

ENV VITE_API_URL=""
ENV NODE_ENV=production

# Explicit path to vite binary — avoids PATH lookup hanging in slim images
RUN ./node_modules/.bin/vite build

# ── Stage 2: Serve ────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine

COPY --from=builder /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
