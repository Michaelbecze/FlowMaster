# Build context is the repository root's frontend/ directory (see infra/docker-compose.yml).
# Dev-mode container: serves via Vite's dev server so the Gateway proxy config
# (vite.config.ts) applies. A production build/nginx stage is added in Phase 7 hardening.
FROM node:20-slim
WORKDIR /app
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
