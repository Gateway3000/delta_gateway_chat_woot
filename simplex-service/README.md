# simplex-service

Runs the official [`simplex-chat`](https://github.com/simplex-chat/simplex-chat)
CLI as a WebSocket bot server for the gateway's SimpleX connector.

The CLI binds its WebSocket port to `127.0.0.1` only, so the container also
runs a `socat` shim that re-exposes it on the container network at
`ws://simplex-chat:5225`. The bot profile/database is persisted in the
`simplex-data` volume (`/data/simplex`).

## Protocol

The CLI speaks JSON over WebSocket: requests are `{"corrId","cmd"}`, replies
carry the matching `corrId`, and async events (incoming messages, new
contacts) arrive with a null `corrId`. The gateway's connector
(`channels/simplex_channel/`) drives this directly — see its `sx_bot_manager.py`.

Key commands the connector uses:
- `/_send @<contactId> json [{"msgContent":{"type":"text","text":"…"}}]` — send text
- `/_address <userId>` / `/_show_address <userId>` — create / read the bot address
- `/_address_settings <userId> {"businessAddress":false,"autoAccept":{"acceptIncognito":false}}` — auto-accept contacts

## First-time setup

Create the bot profile once (interactive — enter a display name, then Ctrl-D):

```bash
docker compose run --rm --entrypoint simplex-chat simplex-chat -d /data/simplex
```

Then start the stack:

```bash
docker compose up -d simplex-chat
```

On connect, the gateway auto-creates the bot's SimpleX **address** and enables
auto-accept of incoming contact requests. The address is logged (look for
`SimpleX bot address ready`) — share it so users can connect to the bot. Once a
user connects (auto-accepted), 1:1 text flows to Chatwoot and agent replies
flow back.

## Build args

- `SIMPLEX_VERSION` (default `v6.5.5`) — the release tag of the CLI binary.
- Architecture is auto-detected (`amd64`→`x86_64`, `arm64`→`aarch64`).
