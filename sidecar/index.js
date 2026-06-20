"use strict";
/**
 * WhatsApp Baileys sidecar — one container == one WhatsApp number.
 *
 * Responsibilities:
 *   - Hold a single WhatsApp Web session (Baileys), persist auth to AUTH_DIR.
 *   - Receive messages -> POST normalized JSON to the gateway's incoming webhook.
 *   - Expose HTTP: POST /send, GET /health, GET /qr, POST /pair, GET /media/:id.
 *
 * The gateway treats this as a webhook source (reuses /ingest/incoming/...),
 * so the Python side only needs parse + send — no long-lived socket in Python.
 *
 * NOTE ON VERSION: pinned to Baileys v6 (widely documented API). v7 introduced
 * breaking changes (see https://whiskey.so/migrate-latest) — if you bump to v7,
 * re-check makeWASocket import, downloadMediaMessage, and connection events.
 */

const express = require("express");
const pino = require("pino");
const QR = require("qrcode-terminal");
const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  downloadMediaMessage,
  fetchLatestBaileysVersion,
} = require("baileys");

// ---- config ---------------------------------------------------------------
const CONNECTOR_ID = process.env.CONNECTOR_ID || "wa1";
const PORT = parseInt(process.env.PORT || "3000", 10);
const AUTH_DIR = process.env.AUTH_DIR || `/data/auth/${CONNECTOR_ID}`;
// Full gateway ingest URL, e.g. http://gateway:8000/ingest/incoming/whatsapp/wa1/webhook
const GATEWAY_INGEST_URL = process.env.GATEWAY_INGEST_URL || "";
// URL other containers use to reach THIS sidecar (for media fetch). Must be the
// docker service name, e.g. http://wa-sidecar-1:3000
const SELF_URL = process.env.SELF_URL || `http://localhost:${PORT}`;
// Optional bearer token protecting /send etc.
const SIDECAR_TOKEN = process.env.SIDECAR_TOKEN || "";
// Optional shared secret sent to the gateway on inbound POSTs.
const INGEST_TOKEN = process.env.INGEST_TOKEN || "";
const MEDIA_TTL_MS = parseInt(process.env.MEDIA_TTL_MS || "600000", 10); // 10 min

const logger = pino({ level: process.env.LOG_LEVEL || "info" });

let sock = null;
let connState = "init"; // init | qr | open | close
let lastQR = null;
let meJid = null;
let lastSeen = null;
let starting = false;

// messageId -> { buf, mime, name, ts }
const mediaCache = new Map();

// ---- WhatsApp session -----------------------------------------------------
async function start() {
  if (starting) return;
  starting = true;
  try {
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    const { version } = await fetchLatestBaileysVersion();
    sock = makeWASocket({ version, auth: state, logger });

    sock.ev.on("creds.update", saveCreds);

    // Pairing-code login (no camera). Set PAIR_NUMBER (digits + country code,
    // no '+'). Code prints in the logs; enter it on the phone via
    // Linked devices -> Link a device -> "Link with phone number instead".
    const pairNumber = (process.env.PAIR_NUMBER || "").replace(/[^0-9]/g, "");
    if (pairNumber && !state.creds.registered) {
      setTimeout(async () => {
        try {
          const code = await sock.requestPairingCode(pairNumber);
          logger.info({ pairing_code: code }, ">>> Enter this pairing code on your phone <<<");
        } catch (e) {
          logger.error({ err: String(e) }, "pairing code request failed");
        }
      }, 3000);
    }

    sock.ev.on("connection.update", (u) => {
      const { connection, lastDisconnect, qr } = u;
      if (qr) {
        lastQR = qr;
        connState = "qr";
        logger.info({ connector: CONNECTOR_ID }, "Scan this QR to log in:");
        QR.generate(qr, { small: true });
      }
      if (connection === "open") {
        connState = "open";
        lastQR = null;
        meJid = sock.user && sock.user.id;
        logger.info({ me: meJid }, "WhatsApp connected");
      }
      if (connection === "close") {
        connState = "close";
        const code =
          lastDisconnect &&
          lastDisconnect.error &&
          lastDisconnect.error.output &&
          lastDisconnect.error.output.statusCode;
        const loggedOut = code === DisconnectReason.loggedOut;
        logger.warn({ code, loggedOut }, "WhatsApp connection closed");
        starting = false;
        if (!loggedOut) setTimeout(start, 2000); // reconnect with backoff
        else logger.error("Logged out — delete the auth volume and re-pair.");
      }
    });

    sock.ev.on("messages.upsert", async ({ messages, type }) => {
      logger.info({ type, count: messages.length }, "messages.upsert event");
      if (type !== "notify" && type !== "append") return;
      for (const m of messages) {
        if (!m.message) {
          logger.warn(
            { id: m.key && m.key.id, from: m.key && m.key.remoteJid },
            "upsert item has no .message (undecryptable or placeholder)"
          );
          continue;
        }
        try {
          await handleInbound(m);
        } catch (e) {
          logger.error({ err: String(e) }, "inbound handling failed");
        }
      }
    });

    // Diagnostics: see whether messages arrive via other events instead.
    sock.ev.on("messages.update", (u) =>
      logger.info({ count: u.length }, "messages.update event")
    );
    sock.ev.on("messaging-history.set", (h) =>
      logger.info(
        { messages: (h.messages || []).length, isLatest: h.isLatest },
        "messaging-history.set event"
      )
    );
  } finally {
    starting = false;
  }
}

const MEDIA_TYPES = [
  "imageMessage",
  "videoMessage",
  "audioMessage",
  "documentMessage",
  "stickerMessage",
];

// Peel WhatsApp wrapper envelopes (disappearing/view-once/edited) to reach content.
function unwrap(message) {
  let msg = message || {};
  for (let i = 0; i < 4; i++) {
    const inner =
      (msg.ephemeralMessage && msg.ephemeralMessage.message) ||
      (msg.viewOnceMessage && msg.viewOnceMessage.message) ||
      (msg.viewOnceMessageV2 && msg.viewOnceMessageV2.message) ||
      (msg.documentWithCaptionMessage && msg.documentWithCaptionMessage.message) ||
      (msg.editedMessage && msg.editedMessage.message);
    if (!inner) break;
    msg = inner;
  }
  return msg;
}

function extractText(message) {
  const msg = unwrap(message);
  const ir = msg.interactiveResponseMessage;
  const tpl = msg.templateMessage && msg.templateMessage.hydratedTemplate;
  return (
    msg.conversation ||
    (msg.extendedTextMessage && msg.extendedTextMessage.text) ||
    (msg.imageMessage && msg.imageMessage.caption) ||
    (msg.videoMessage && msg.videoMessage.caption) ||
    (msg.documentMessage && msg.documentMessage.caption) ||
    (msg.buttonsResponseMessage && msg.buttonsResponseMessage.selectedDisplayText) ||
    (msg.listResponseMessage && msg.listResponseMessage.title) ||
    (msg.templateButtonReplyMessage && msg.templateButtonReplyMessage.selectedDisplayText) ||
    (ir && ir.body && ir.body.text) ||
    (msg.buttonsMessage && msg.buttonsMessage.contentText) ||
    (msg.listMessage && msg.listMessage.description) ||
    (tpl && tpl.hydratedContentText) ||
    ""
  );
}

async function handleInbound(m) {
  if (!m.message) return;
  if (m.key && m.key.fromMe) return;
  const jid = (m.key && m.key.remoteJid) || "";
  if (jid.endsWith("@g.us")) return; // 1:1 only — skip groups (TODO if needed)
  if (jid === "status@broadcast") return;
  lastSeen = Date.now();

  const content = unwrap(m.message);
  const attachments = [];
  const mkey = Object.keys(content).find((k) => MEDIA_TYPES.includes(k));
  if (mkey) {
    try {
      const buf = await downloadMediaMessage(
        m,
        "buffer",
        {},
        { logger, reuploadRequest: sock.updateMediaMessage }
      );
      const id = m.key.id;
      const node = content[mkey];
      const mime = node.mimetype || "application/octet-stream";
      const name = node.fileName || id;
      mediaCache.set(id, { buf, mime, name, ts: Date.now() });
      attachments.push({
        id,
        type: mkey.replace("Message", ""),
        mimetype: mime,
        filename: name,
        url: `${SELF_URL}/media/${id}`,
      });
    } catch (e) {
      logger.error({ err: String(e) }, "media download failed");
    }
  }

  const kind = mkey || Object.keys(content)[0] || "unknown";
  let text = extractText(m.message);
  if (!text && attachments.length === 0) text = `[unsupported: ${kind}]`;

  logger.info(
    { from: jid, message_id: m.key.id, kind, chars: text.length, attachments: attachments.length },
    "inbound message"
  );

  const payload = {
    message_id: m.key.id,
    from: { id: jid, name: m.pushName || "" },
    text,
    timestamp: Number(m.messageTimestamp) || Math.floor(Date.now() / 1000),
    attachments,
  };
  await postToGateway(payload);
}

async function postToGateway(payload) {
  if (!GATEWAY_INGEST_URL) {
    logger.warn("GATEWAY_INGEST_URL not set — dropping inbound message");
    return;
  }
  try {
    const res = await fetch(GATEWAY_INGEST_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(INGEST_TOKEN ? { "x-ingest-token": INGEST_TOKEN } : {}),
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok && res.status !== 204) {
      logger.error({ status: res.status }, "gateway rejected inbound");
    }
  } catch (e) {
    logger.error({ err: String(e) }, "failed to POST inbound to gateway");
  }
}

function toJid(to) {
  if (!to) return "";
  if (String(to).includes("@")) return String(to);
  return `${String(to).replace(/[^0-9]/g, "")}@s.whatsapp.net`;
}

// ---- HTTP API -------------------------------------------------------------
const app = express();
app.use(express.json({ limit: "25mb" }));

function auth(req, res, next) {
  if (!SIDECAR_TOKEN) return next();
  const h = req.headers.authorization || "";
  if (h === `Bearer ${SIDECAR_TOKEN}`) return next();
  return res.status(401).json({ error: "unauthorized" });
}

app.get("/health", (req, res) => {
  res.json({
    connector_id: CONNECTOR_ID,
    state: connState,
    connected: connState === "open",
    me: meJid,
    last_seen: lastSeen,
  });
});

app.get("/qr", (req, res) => {
  res.json({ connector_id: CONNECTOR_ID, state: connState, qr: lastQR });
});

// Pairing-code login (alternative to QR). Only valid before registration.
app.post("/pair", auth, async (req, res) => {
  const phone = req.body && req.body.phone;
  if (!sock || !phone)
    return res.status(400).json({ error: "phone required, socket must be up" });
  try {
    const code = await sock.requestPairingCode(String(phone).replace(/[^0-9]/g, ""));
    res.json({ pairing_code: code });
  } catch (e) {
    res.status(500).json({ error: String(e) });
  }
});

app.post("/send", auth, async (req, res) => {
  if (!sock || connState !== "open")
    return res.status(503).json({ error: "not connected", state: connState });
  const { to, text, attachments = [] } = req.body || {};
  const jid = toJid(to);
  if (!jid) return res.status(400).json({ error: "recipient 'to' required" });
  try {
    const ids = [];
    if (text && String(text).trim()) {
      const r = await sock.sendMessage(jid, { text: String(text) });
      if (r && r.key) ids.push(r.key.id);
    }
    for (const a of attachments) {
      const url = a.data_url || a.url;
      if (!url) continue;
      const resp = await fetch(url);
      const buf = Buffer.from(await resp.arrayBuffer());
      const mime =
        a.mime_type || a.mimetype || resp.headers.get("content-type") || "application/octet-stream";
      let content;
      if (mime.startsWith("image/")) content = { image: buf, caption: a.caption || undefined };
      else if (mime.startsWith("video/")) content = { video: buf, caption: a.caption || undefined };
      else if (mime.startsWith("audio/")) content = { audio: buf, mimetype: mime };
      else content = { document: buf, mimetype: mime, fileName: a.filename || "file" };
      const r = await sock.sendMessage(jid, content);
      if (r && r.key) ids.push(r.key.id);
    }
    if (ids.length === 0) return res.status(400).json({ error: "nothing to send" });
    res.json({ ok: true, ids });
  } catch (e) {
    logger.error({ err: String(e) }, "send failed");
    res.status(500).json({ error: String(e) });
  }
});

app.get("/media/:id", (req, res) => {
  const item = mediaCache.get(req.params.id);
  if (!item) return res.status(404).json({ error: "not found or expired" });
  res.setHeader("Content-Type", item.mime);
  res.setHeader("Content-Disposition", `inline; filename="${item.name}"`);
  res.send(item.buf);
});

// evict stale media
setInterval(() => {
  const now = Date.now();
  for (const [id, v] of mediaCache) if (now - v.ts > MEDIA_TTL_MS) mediaCache.delete(id);
}, 60000).unref();

app.listen(PORT, () => logger.info({ port: PORT, connector: CONNECTOR_ID }, "sidecar listening"));
start();
