# ── Stage 1: build ───────────────────────────────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app

# Install deps first (layer-cached unless package.json changes)
COPY frontend/package*.json ./
RUN npm ci

# Copy only source files — node_modules is excluded by .dockerignore so
# the COPY below will never overwrite the freshly installed (executable) modules
COPY frontend/index.html        ./index.html
COPY frontend/tsconfig*.json    ./
COPY frontend/vite.config.ts    ./vite.config.ts
COPY frontend/tailwind.config.ts ./tailwind.config.ts
COPY frontend/postcss.config.js  ./postcss.config.js
COPY frontend/src               ./src
COPY frontend/public            ./public

RUN npm run build

# ── Stage 2: serve with nginx ─────────────────────────────────────────────────
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
