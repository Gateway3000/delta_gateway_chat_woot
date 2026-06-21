# Connector patterns — choosing an implementation approach

A connector ("channel") is a **plugin** that teaches the gateway how to move
messages between one chat platform and Chatwoot. The gateway owns the pipeline,
the durable queues, the workers, and the Chatwoot side. A connector author only
implements two things: **how messages get in** and **how they go out**.

Before writing any code, the only real decision is: **how does your platform let
you receive and send messages?** Every connector in this codebase is one of a
few archetypes along two independent axes. Figure out where your service lands on
each axis, copy the closest existing connector, and most of the work is done.

## Axis 1 — How do messages come IN (platform → us)?

This is decided entirely by **what your platform supports**, not by preference.

| If your platform…                                       | Pattern                   | Copy from         | What you run                                                   |
| ------------------------------------------------------- | ------------------------- | ----------------- | ------------------------------------------------------------- |
| can POST to a URL when a message arrives                | **Webhook**               | telegram, whatsapp | nothing — the gateway already exposes the inbound URL          |
| only offers a long-lived socket/stream (no webhook)     | **Persistent connection** | signal, simplex   | a background loop that holds the connection open and drains it |
| must be checked on a schedule (mailbox-style)           | **Polling**               | email             | a watcher that polls on a timer                                |
| has a native library you run in-process                 | **In-process / native**   | delta_chat        | the library inside the gateway, firing a callback per message  |

Nuances inside the webhook pattern:

- If the platform needs you to *tell it* where to send webhooks (register a URL),
  add a small registration step at startup (telegram does this).
- If a helper sidecar receives from the platform and forwards to you (because the
  platform's protocol is awkward), it's still "webhook" from the gateway's point
  of view — the sidecar just POSTs in (whatsapp).

## Axis 2 — How do messages go OUT (us → platform)?

| If you reach your platform by…                          | Pattern              | Copy from                       |
| ------------------------------------------------------- | -------------------- | ------------------------------- |
| calling a normal HTTP API                               | **Direct API call**  | telegram, imessage              |
| a separate helper process you run (sidecar/daemon)      | **Sidecar/daemon**   | whatsapp, signal, session, simplex |
| a native library in-process                             | **Native send**      | delta_chat                      |
| sending email                                           | **SMTP**             | email                           |

The two axes are independent:

- **Signal** — persistent-connection in *and* daemon out (same daemon serves both).
- **WhatsApp** — webhook in *and* sidecar out.
- **Telegram** — webhook in *and* direct-API out.

## Do you need a sidecar at all?

Use a **sidecar/helper service** (like `sidecar/`, `signal-bridge/`, `session/`,
`simplex-service/`) only when the platform can't be talked to cleanly from Python
— e.g. it needs a specific SDK in another language, a persistent native client,
or a CLI. Otherwise talk to the API directly.

The sidecar handles the messy platform protocol; it exposes a simple
"receive → POST to gateway" plus "expose a `/send` endpoint" interface, and your
connector treats it as just another HTTP endpoint.

## Two more questions that shape your connector

- **Attachments?** If your platform only does text (session, simplex), skip all
  attachment handling. If it does media, add an attachments module to convert
  files both ways (inbound: platform → Chatwoot; outbound: fetch from Chatwoot →
  platform).
- **Stateful sessions?** If you keep a live per-account client/connection
  (telegram bot sessions, signal/simplex sockets), you'll have a "bot manager"
  that owns those. If every send is a stateless HTTP call (whatsapp, email), you
  don't need one.

## What's the same for everyone (you don't design this)

No matter which patterns you pick, the gateway gives you a fixed spine, so all
you really write is "parse a message" and "send a message":

- A **plugin contract** (6 methods) — your connector is a thin facade; the
  gateway discovers it automatically via an entry point.
- A **durable queue in the middle** — you don't deliver messages directly; you
  put a normalized message on a queue and the gateway's workers deliver it, with
  **retries and deduplication handled for you**.
- A **normalized message format** (the "Envelope") — you translate your
  platform's payload to/from it; everything downstream (Chatwoot, routing,
  anonymization) is shared.

## The bottom line

The whole job reduces to:

1. Pick your **inbound** pattern (Axis 1).
2. Pick your **outbound** pattern (Axis 2).
3. Decide whether you need a **sidecar**, **attachments**, and a **bot manager**.
4. Copy the closest existing connector and rewrite the translation logic for
   your platform.

| Connector  | Inbound               | Outbound      | Sidecar          | Attachments | Stateful |
| ---------- | --------------------- | ------------- | ---------------- | ----------- | -------- |
| telegram   | webhook (registered)  | direct API    | no               | yes         | yes      |
| whatsapp   | webhook (sidecar in)  | sidecar       | `sidecar/`       | yes         | no       |
| imessage   | webhook (manual URL)  | direct API    | BlueBubbles      | yes         | yes      |
| signal     | persistent connection | daemon        | `signal-bridge/` | yes         | yes      |
| simplex    | persistent connection | daemon        | `simplex-service/` | no        | yes      |
| session    | webhook (sidecar in)  | sidecar       | `session/`       | no          | yes      |
| email      | polling (IMAP)        | SMTP          | no               | yes         | no       |
| delta_chat | in-process / native   | native        | no               | yes         | no       |
