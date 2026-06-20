# Standalone crate: presage is pulled as a git dependency, so the build
# context is just this directory (no vendored workspace needed).
FROM rust:1.95-bookworm AS builder

# libsignal / curve25519 / prost build needs a protobuf compiler and a C
# toolchain; sqlite is bundled via the patched rusqlite.
RUN apt-get update && apt-get install -y --no-install-recommends \
        protobuf-compiler \
        cmake \
        clang \
        pkg-config \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY . .
RUN cargo build --release

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /src/target/release/signal-bridge /usr/local/bin/signal-bridge

# The linked session is persisted here — mount a volume to keep it.
ENV SIGNAL_DB_PATH=/data/signal.db3
VOLUME ["/data"]

EXPOSE 8080
ENTRYPOINT ["signal-bridge"]
CMD ["serve", "--listen", "0.0.0.0:8080"]
