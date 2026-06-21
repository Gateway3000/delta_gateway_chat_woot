# Runs the official simplex-chat CLI as a WebSocket server. The CLI binds the
# WS port to localhost only, so a socat shim re-exposes it on the container's
# network interface for the gateway to reach.
FROM ubuntu:22.04

ARG TARGETARCH
ARG SIMPLEX_VERSION=v6.5.5

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        socat \
        zlib1g \
        libgmp10 \
        libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Download the release binary matching the build architecture.
RUN set -eux; \
    arch="${TARGETARCH:-$(dpkg --print-architecture)}"; \
    case "$arch" in \
      amd64) sx_arch=x86_64 ;; \
      arm64) sx_arch=aarch64 ;; \
      *) echo "unsupported arch: $arch" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o /usr/local/bin/simplex-chat \
      "https://github.com/simplex-chat/simplex-chat/releases/download/${SIMPLEX_VERSION}/simplex-chat-ubuntu-22_04-${sx_arch}"; \
    chmod +x /usr/local/bin/simplex-chat

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# The profile database lives here — mount a volume to persist it.
ENV SIMPLEX_DB=/data/simplex
VOLUME ["/data"]

EXPOSE 5225
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
