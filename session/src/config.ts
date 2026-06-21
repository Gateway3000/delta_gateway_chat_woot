/**
 * Configuration for the Session <-> webhook bridge.
 *
 * Mirrors the shape of the Python `WebhookConfig` dataclass from the
 * BitChat/Nostr REST bridge: a callback URL the bot POSTs inbound
 * messages to, an outbound HTTP path the bot listens on for replies,
 * and a "source" marker used to avoid relaying its own traffic back
 * into itself if the same webhook is reused bidirectionally.
 */
export interface WebhookConfig {
  /** URL to POST inbound Session DMs to. */
  callbackUrl: string
  /** Display name for the bot's Session profile. */
  nick: string
  /** Local HTTP path that accepts outbound replies to relay to Session. Default: /webhook */
  path: string
  /** Value of `source` in incoming POST bodies that should be ignored (loop prevention). */
  ignoreSource: string
  /** Timeout in ms for the outbound POST to callbackUrl. */
  timeoutMs: number
  /** Host to bind the local HTTP server to. */
  host: string
  /** Port to bind the local HTTP server to. */
  port: number
}

export const defaultWebhookConfig = (overrides: Partial<WebhookConfig> = {}): WebhookConfig => ({
  callbackUrl: overrides.callbackUrl ?? '',
  nick: overrides.nick ?? 'session-webhook-bot',
  path: overrides.path ?? '/webhook',
  ignoreSource: overrides.ignoreSource ?? 'session_bot',
  timeoutMs: overrides.timeoutMs ?? 10_000,
  host: overrides.host ?? '127.0.0.1',
  port: overrides.port ?? 8080,
})
