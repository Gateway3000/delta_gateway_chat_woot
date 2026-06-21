import { Session, Poller, ready } from '@session.js/client'
import type { Message } from '@session.js/types'
import { SessionJsError, SessionValidationError } from '@session.js/errors'
import type { WebhookConfig } from './config'

await ready

interface InboundWebhookPayload {
  text: string
  sender: string
  channel: 'session_dm' | 'session_group'
  groupId?: string
  messageId: string
  timestamp: number
  source: string
}

interface OutboundReplyPayload {
  /** Session ID to send the reply to. Required. */
  to: string
  /** Message text to send. */
  text: string
  /** Optional source marker, echoed back so you can filter loops on your webhook server. */
  source?: string
}

async function postJson(url: string, payload: unknown, timeoutMs: number): Promise<{ status: number; body: string }> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
    const body = await res.text()
    return { status: res.status, body }
  } finally {
    clearTimeout(timer)
  }
}

export class SessionWebhookBridge {
  readonly session: Session
  private readonly poller: Poller
  private readonly config: WebhookConfig
  private started = false

  constructor(mnemonic: string, config: WebhookConfig) {
    this.config = config
    this.session = new Session()

    try {
      this.session.setMnemonic(mnemonic, config.nick)
    } catch (e) {
      if (e instanceof SessionValidationError) {
        throw new Error(`Invalid mnemonic for bot account: ${e.code}`)
      }
      throw e
    }

    this.poller = new Poller() // default 2.5s interval
    this.session.addPoller(this.poller)
  }

  get sessionId(): string {
    return this.session.getSessionID()
  }

  /** Start listening for inbound Session messages and forward each one to the webhook. */
  start(): void {
    if (this.started) return
    this.started = true

    console.log(`session id: ${this.sessionId}`)
    console.log(`bridging Session DMs to ${this.config.callbackUrl}`)

    this.session.on('message', (msg: Message) => {
      void this.handleInboundMessage(msg)
    })
  }

  private async handleInboundMessage(msg: Message): Promise<void> {
    if (!msg.text) return // skip non-text (attachments-only, typing, receipts, etc.)

    const payload: InboundWebhookPayload = {
      text: msg.text,
      sender: msg.from,
      channel: msg.type === 'group' ? 'session_group' : 'session_dm',
      groupId: msg.type === 'group' ? msg.groupId : undefined,
      messageId: msg.id,
      timestamp: msg.timestamp,
      source: this.config.ignoreSource,
    }

    console.log(`[in] ${payload.sender}: ${payload.text}`)

    try {
      const { status, body } = await postJson(this.config.callbackUrl, payload, this.config.timeoutMs)
      console.log(`webhook delivery status=${status} response=${body.slice(0, 160)}`)
    } catch (err) {
      console.error(`webhook delivery failed:`, err instanceof Error ? err.message : err)
    }
  }

  /** Send a reply out to Session. Called by the local HTTP server below. */
  async sendReply(payload: OutboundReplyPayload): Promise<{ messageHash: string; timestamp: number }> {
    try {
      const result = await this.session.sendMessage({
        to: payload.to,
        text: payload.text,
      })
      console.log(`[out] -> ${payload.to}: ${payload.text}`)
      return result
    } catch (e) {
      if (e instanceof SessionValidationError) {
        throw new Error(`Invalid outbound payload (${e.code}): check 'to' is a valid Session ID`)
      }
      if (e instanceof SessionJsError) {
        throw new Error(`Session.js error sending reply: ${e.code}`)
      }
      throw e
    }
  }
}

export type { InboundWebhookPayload, OutboundReplyPayload }
