# Connector setup guide

How to set up each connector, one by one. Some connectors are pure
configuration; others require **manual UI steps ("clickops")** — scanning a QR
code, pasting a webhook URL into another app, or linking a phone. Those are
called out explicitly per connector.

- [The three IDs](#the-three-ids)
- [Before you start (common steps)](#before-you-start-common-steps)
- [Telegram](#telegram)
- [WhatsApp](#whatsapp)
- [iMessage](#imessage)
- [Signal](#signal)
- [SimpleX](#simplex)
- [Session](#session)
- [Delta Chat](#delta-chat)
- [Email](#email)

---

## The three IDs

Every connector config ties together three IDs:

- **`connector_id`** — *your* name for one connector instance (e.g. `tg1`, `wa1`):
  which bot/number/mailbox. Used in webhook URLs and the idempotency key, so
  **don't change it in production after first launch**.
- **`cw_inbox_id`** — the Chatwoot **inbox** (one API inbox per connector) where
  messages land and agents reply.
- **`cw_account_id`** — the Chatwoot **account** (workspace) that the inbox lives in.

```
connector_id (tg1)  ──►  cw_inbox_id (888)  ──►  cw_account_id (123)
 platform side: which bot   Chatwoot inbox        Chatwoot workspace
```

One `connector_id` maps to one `cw_inbox_id`, which lives in one `cw_account_id`.

## Before you start (common steps)

These apply to **every** connector. Do them once, plus once per connector where
noted.

### 1. Chatwoot: create an API inbox (per connector) — *clickops*

Each connector instance maps to one Chatwoot **API channel** inbox.

1. In Chatwoot: **Settings → Inboxes → Add Inbox → API**.
2. Give it a name, finish the wizard.
3. Read the two IDs you'll need from the browser URL:
   `https://<chatwoot>/app/accounts/{cw_account_id}/settings/inboxes/{cw_inbox_id}`
   - `cw_account_id` — the account number.
   - `cw_inbox_id` — the inbox number.

### 2. Chatwoot: get an access token — *clickops*

**Profile Settings → Access Token** (bottom of the page). Put it in
`CHATWOOT_ACCESS_TOKEN`. Also set `CHATWOOT_BASE_URL` to your Chatwoot URL.

### 3. Chatwoot: set the outbound webhook (per connector) — *clickops*

So agent replies reach the gateway, configure the inbox/account webhook to:

```
https://<your-domain>/ingest/outgoing/{channel}/{cw_account_id}/webhook
```

`{channel}` is the connector name exactly (`telegram`, `whatsapp`, `imessage`,
`signal`, `simplex`, `session`, `delta_chat`, `email`). For local development,
expose the gateway publicly with a tunnel (Cloudflared / Serveo / ngrok) and use
that as `WH_DOMAIN` and as the host in the webhook URL — see the main README,
section 5.1.

### 4. Enable the connector

List the connectors to load in `CHANNELS` (JSON array). If unset, **all**
discovered connectors load.

```bash
CHANNELS='["telegram", "whatsapp"]'
```

> All values inside the `*_CONFIG` JSON blobs must be quoted strings, even
> numeric IDs.

---

## Telegram

Talks to the Telegram Bot API directly. The gateway **registers the webhook for
you** at startup, so there is no webhook clickops on the Telegram side.

**Clickops:** create the bot in **@BotFather** (`/newbot`) and copy the token.

**Config:**

```bash
BOTS_CONFIG='[{"connector_id":"tg1","bot_token":"0123456789:ABC...","cw_account_id":"123","cw_inbox_id":"888"}]'
SECRET_TOKEN=ABCDEFGHIJKLMNOP   # letters/digits only; sent in the webhook header for security
WH_DOMAIN=https://your-domain.com
```

The gateway calls `setWebhook` on boot, pointing Telegram at
`WH_DOMAIN/ingest/incoming/telegram/{connector_id}/webhook`. Don't forget the
Chatwoot outbound webhook (common step 3) with `channel = telegram`.

---

## WhatsApp

Runs through the **`wa-sidecar` container** (Baileys). The sidecar logs into a
WhatsApp account and POSTs incoming messages to the gateway; the gateway calls
the sidecar's `/send` API for replies. One sidecar container per number.

**Clickops:** link the WhatsApp account to the sidecar, either by:
- **QR code** — start the sidecar and scan the QR printed in its logs from your
  phone (**WhatsApp → Linked Devices → Link a Device**), or
- **Pairing code** — set `WA1_PAIR_NUMBER` (digits + country code, no `+`) and
  enter the code the sidecar logs into your phone instead of scanning.

**Config:**

```bash
WHATSAPP_CONFIG='[{"connector_id":"wa1","sidecar_url":"http://wa-sidecar-1:3000","cw_account_id":"1","cw_inbox_id":"1"}]'
SIDECAR_TOKEN=some_shared_secret      # gateway -> sidecar auth
WA_SIDECAR_TOKEN=some_shared_secret   # MUST equal SIDECAR_TOKEN
WA_INGEST_TOKEN=some_ingest_secret    # sidecar -> gateway auth
WA1_PAIR_NUMBER=                      # leave empty for QR login
```

The sidecar service (`wa-sidecar-1` in `docker-compose.yml`) is pre-wired to POST
to `…/ingest/incoming/whatsapp/wa1/webhook`. After a logout you must delete the
`wa1_auth` volume and re-link.

---

## iMessage

Talks to a self-hosted **BlueBubbles** server running on a Mac. There is no
central API and **no way to register the webhook programmatically** — it must be
added by hand in the BlueBubbles app.

**Clickops (two parts):**
1. Install and configure **BlueBubbles Server** on a Mac signed into iMessage;
   set a server password.
2. Add the gateway as a webhook: in the BlueBubbles Server app, **API & Webhooks
   → Manage → Add Webhook**, paste
   `WH_DOMAIN/ingest/incoming/imessage/{connector_id}/webhook`, and subscribe to
   the **New Message** event. (The gateway logs this exact URL at startup so you
   don't have to construct it.)

**Config:**

```bash
IMESSAGE_BOTS_CONFIG='[{"connector_id":"im1","server_url":"https://bluebubbles.example.com","server_password":"YOUR_BB_PASSWORD","cw_account_id":"123","cw_inbox_id":"777"}]'
WH_DOMAIN=https://your-domain.com
```

Optional per-bot `send_method`: `"apple-script"` (default) or `"private-api"`.

---

## Signal

Runs through the **`signal-bridge` container** (a presage-based daemon speaking
JSON over TCP). It holds a persistent connection — there is no webhook. One
bridge instance per Signal number.

**Clickops:** link the bridge as a secondary device to your Signal account.
Run the link command once and scan the emitted QR from your phone
(**Signal → Settings → Linked Devices → Link New Device**):

```bash
docker compose run --rm signal-bridge link
```

The linked session is stored in the `signal-data` volume and survives restarts.

**Config:**

```bash
SIGNAL_BOTS_CONFIG='[{"connector_id":"sig1","number":"+491234567","host":"signal-bridge","port":8080,"cw_account_id":"123","cw_inbox_id":"666"}]'
```

`number` is the linked account; `host`/`port` is how the gateway reaches the
bridge. A second number requires a second bridge service with its own
host/port/volume.

---

## SimpleX

Runs through the **`simplex-chat` container** (official CLI as a WebSocket bot).
Persistent connection, no webhook. One SimpleX profile per instance.

**Clickops:** create the bot profile once (enter a display name, then `Ctrl-D`),
then **share the bot's SimpleX address** with users so they can start a chat:

```bash
# create the profile once
docker compose run --rm --entrypoint simplex-chat simplex-chat -d /data/simplex
docker compose up -d simplex-chat
```

On connect the gateway auto-creates the bot's SimpleX address and enables
auto-accept of contact requests. The address is printed in the logs (look for
`SimpleX bot address ready`) — share that with users.

**Config:**

```bash
SIMPLEX_CONFIG='[{"connector_id":"sx1","ws_url":"ws://simplex-chat:5225","user_id":1,"cw_account_id":"123","cw_inbox_id":"555"}]'
```

`user_id` is the CLI's local user id (`1` for a fresh profile). The profile DB
lives in the `simplex-data` volume.

---

## Session

Runs through the **`session-bridge` container** (Bun/TS). It posts incoming
messages to a static per-connector webhook URL and exposes a `/send` API; no
remote webhook registration.

**Clickops:** minimal. You supply the Session account **mnemonic** (the bridge
restores the account from it). You can read back the bot's Session ID / nick via
the gateway endpoint `GET /ingest/session/{connector_id}/bot_id` and share the
Session ID with users.

**Config:**

```bash
SESSION_MNEMONIC="your session recovery phrase"
SESSION_BOTS_CONFIG='[{"connector_id":"session1","webhook_url":"http://session-bridge:8080/webhook","cw_account_id":"2","cw_inbox_id":"1"}]'
```

`webhook_url` is the bridge's own ingest URL (in-network), not a public one.

---

## Delta Chat

An email-based messenger. Runs **in-process** via the native deltachat RPC
server (no sidecar), or temporarily through the bundled legacy `deltawoot` bridge
during migration. Delta Chat owns its own identity mapping.

**Clickops:** obtain a Delta Chat account — i.e. an email/chatmail address +
password (from any chatmail server or IMAP/SMTP mailbox). Optionally users add
the bot by scanning its **secure-join QR**, served at
`GET /deltachat/{connector_id}/secure-join-qr.svg`.

**Config (native mode):**

```bash
ENABLE_NATIVE_DELTACHAT_CHANNEL=true
DELTA_CHAT_ACCOUNTS='[{"connector_id":"delta-client-1","address":"bot1@example.org","password":"secret","display_name":"Support Bot 1","avatar_path":"/data/bot1/avatar.jpg","cw_account_id":"1","cw_inbox_id":"5"}]'
DELTACHAT_ACCOUNTS_DIR=/data/deltachat
DELTACHAT_RPC_SERVER_PATH=deltachat-rpc-server
```

**Auto-provision a chatmail account (`dcaccount_url`):** instead of supplying
`address`/`password`, point a connector at a chatmail server's account-creation
URL and the gateway provisions a fresh account on startup:

```bash
DELTA_CHAT_ACCOUNTS='[{"connector_id":"delta-client-1","dcaccount_url":"dcaccount:https://chat.example.org/new","cw_account_id":"1","cw_inbox_id":"5"}]'
```

The gateway POSTs to the URL (stripping the `dcaccount:` prefix) and expects a
JSON `{email, password}` back, which it uses as the account credentials.
`display_name`/`avatar_path` from the config still apply. Use either
`dcaccount_url` **or** `address`+`password`, not both.

**Migration mode:** set `ENABLE_NATIVE_DELTACHAT_CHANNEL=false` and add
`"bridge_url":"http://deltawoot:5000"` to each account; start the legacy relay
with `docker compose --profile legacy-deltachat up -d`.

> Note: the outbound Chatwoot webhook channel name is `delta_chat`
> (underscore), even though the entry point is registered as `deltachat`.

---

## Email

Polls a mailbox over **IMAP** and sends replies over **SMTP**. No sidecar, no
webhook — the gateway polls on a timer.

**Clickops:** in the mail provider, **enable IMAP** and (for Gmail and similar)
create an **app password** to use instead of the account password.

**Config:**

```bash
MAILBOXES_CONFIG='[{"connector_id":"e1","cw_account_id":"24","cw_inbox_id":"12","imap_username":"you@example.com","imap_password":"16-digit-app-password","smtp":{"smtp_username":"you@example.com","smtp_from":"you@example.com"}}]'
```

Defaults assume Gmail (`imap.gmail.com:993`, `smtp.gmail.com:587`); override
`imap_host`/`imap_port`/`smtp_host`/`smtp_port` for other providers.
`smtp_password` defaults to `imap_password` if omitted. Optional:
`imap_mailbox` (default `INBOX`), `processed_folder`, `poll_interval_seconds`.

---

## Quick reference

| Connector  | Helper service     | Inbound       | Manual (clickops) step                                  |
| ---------- | ------------------ | ------------- | ------------------------------------------------------- |
| Telegram   | none               | webhook       | create bot in @BotFather                                |
| WhatsApp   | `wa-sidecar`       | webhook       | scan QR / enter pairing code to link the account        |
| iMessage   | BlueBubbles (Mac)  | webhook       | install BlueBubbles + paste webhook URL in its UI       |
| Signal     | `signal-bridge`    | persistent    | `signal-bridge link`, scan QR (Linked Devices)          |
| SimpleX    | `simplex-chat`     | persistent    | create profile once, share bot address                  |
| Session    | `session-bridge`   | webhook       | provide account mnemonic; share bot Session ID          |
| Delta Chat | none (native RPC)  | in-process    | get a chatmail/email account; optional secure-join QR   |
| Email      | none               | polling (IMAP)| enable IMAP + create app password                       |

Every connector also needs the [common steps](#before-you-start-common-steps):
a Chatwoot API inbox, an access token, the outbound webhook, and an entry in
`CHANNELS`.
