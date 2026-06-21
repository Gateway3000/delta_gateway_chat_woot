import type { SessionWebhookBridge, OutboundReplyPayload } from './bridge'
import type { WebhookConfig } from './config'

function jsonResponse(status: number, payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function isOutboundReplyPayload(value: unknown): value is OutboundReplyPayload {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  return typeof v.to === 'string' && v.to.length > 0 && typeof v.text === 'string'
}

export function startServer(bridge: SessionWebhookBridge, config: WebhookConfig) {
  const server = Bun.serve({
    hostname: config.host,
    port: config.port,
    async fetch(req) {
      const url = new URL(req.url)

      if (req.method === 'GET' && url.pathname === '/health') {
        return jsonResponse(200, { ok: true, nick: config.nick, sessionId: bridge.sessionId })
      }

      if (req.method === 'POST' && url.pathname === config.path) {
        let body: unknown
        try {
          body = await req.json()
        } catch {
          return jsonResponse(400, { error: 'invalid json' })
        }

        if (typeof body === 'object' && body !== null && (body as Record<string, unknown>).source === config.ignoreSource) {
          return jsonResponse(202, { ok: true, ignored: 'own webhook' })
        }

        if (!isOutboundReplyPayload(body)) {
          return jsonResponse(400, { error: "payload must include 'to' (Session ID) and 'text'" })
        }

        try {
          const { messageHash, timestamp } = await bridge.sendReply(body)
          return jsonResponse(200, { ok: true, messageHash, timestamp })
        } catch (err) {
          return jsonResponse(502, { ok: false, error: err instanceof Error ? err.message : String(err) })
        }
      }

      return jsonResponse(404, { error: 'not found' })
    },
  })

  console.log(`webhook bot listening on http://${config.host}:${config.port}${config.path}`)
  console.log(`posting inbound Session DMs to ${config.callbackUrl}`)

  return server
}
