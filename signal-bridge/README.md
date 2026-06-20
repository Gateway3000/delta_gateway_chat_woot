# signal-bridge

A thin, line-oriented bridge over [presage](https://github.com/whisperfish/presage)
that lets a non-Rust parent process drive a real Signal account over
**stdin/stdout** instead of an HTTP server.

- **stdout** — newline-delimited JSON (NDJSON), one event per line.
- **stdin** — one JSON object per line to send a message.
- **stderr** — human/diagnostic logs only (so stdout stays machine-readable).

The linked session is stored in an encrypted SQLite file (`--db-path`,
default `/data/signal.db3`).

## Commands

```
signal-bridge link [--device-name NAME]   # link as a secondary device
signal-bridge whoami                       # print linked account identifiers
signal-bridge daemon                       # stream incoming + accept outgoing
```

Global options (also env vars): `--db-path`/`SIGNAL_DB_PATH`,
`--passphrase`/`SIGNAL_PASSPHRASE`, `--servers`/`SIGNAL_SERVERS`
(`production` | `staging`).

## Linking

```
signal-bridge link
```
Emits the provisioning URL:
```json
{"type":"link","url":"sgnl://linkdevice?uuid=...&pub_key=..."}
```
Render it as a QR code (or paste the URL) and scan it from the phone:
**Signal → Settings → Linked Devices → Link New Device**. On success:
```json
{"type":"linked","number":"+49...","service_ids":"aci=...,pni=..."}
```

## Daemon protocol

On start it emits a `linked` event then `{"type":"ready"}`.

### Incoming (stdout)
Only **1:1 text** messages are surfaced (groups, reactions, receipts, typing,
sync and empty bodies are dropped):
```json
{"type":"message","source_uuid":"2647ff35-…","source_name":"Ellie","timestamp":1781965264745,"message":"Hi"}
```
Other lifecycle events: `{"type":"queue_empty"}`, `{"type":"error","error":"…"}`.

### Outgoing (stdin)
One JSON object per line:
```json
{"recipient":"2647ff35-bb65-4459-90d8-c5c832c04d08","message":"Hello back"}
```
`recipient` is a bare UUID (treated as an ACI) or a full service-id string
(`PNI:<uuid>`). Each send yields:
```json
{"type":"send_result","ok":true,"recipient":"2647ff35-…","timestamp":1781965272850}
```

## Building

This is a standalone crate; `presage` and `presage-store-sqlite` are pulled as
pinned git dependencies (see `Cargo.toml`). The `[patch.crates-io]` overrides
required by the libsignal stack live in this crate's own manifest, since patches
are not inherited from a dependency's workspace.

```bash
# from signal-bridge/
cargo build --release
```

## Docker

The image's default command is `serve --listen 0.0.0.0:8080`, so it runs the
TCP protocol — that's how the gateway's `signal-bridge` compose service runs it.

```bash
# from signal-bridge/
docker build -t signal-bridge .

# link once (interactive; render the emitted URL as a QR):
docker run --rm -it -v signal-data:/data signal-bridge link

# serve over TCP (the gateway connects to signal-bridge:8080):
docker run --rm -p 8080:8080 -v signal-data:/data signal-bridge
```

In this repo the gateway runs it via docker-compose; link once with:

```bash
docker compose run --rm signal-bridge link
```

The `/data` volume persists the linked session across restarts. `daemon`
(stdin/stdout) remains available for local debugging.
