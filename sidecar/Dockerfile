# Debian slim (glibc), not alpine (musl): Baileys' prebuilt deps install cleanly.
# git is required: Baileys pulls `libsignal` from a git+https URL.
FROM node:20-bookworm-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends git ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund

COPY index.js ./

# Auth state persists here; mount a volume per instance
ENV AUTH_DIR=/data/auth
RUN mkdir -p /data/auth

EXPOSE 3000
CMD ["node", "index.js"]
