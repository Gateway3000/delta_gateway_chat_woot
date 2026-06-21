import { ready } from '@session.js/client'
import { SessionWebhookBridge } from './bridge'
import { defaultWebhookConfig } from './config'
import { startServer } from './server'

await ready

interface CliArgs {
  mnemonic: string
  webhookUrl: string
  host: string
  port: number
  path: string
  nick: string
  timeoutMs: number
}

function parseArgs(argv: string[]): CliArgs {
  const get = (flag: string): string | undefined => {
    const i = argv.indexOf(flag)
    return i !== -1 ? argv[i + 1] : undefined
  }

  const mnemonic = get('--mnemonic') ?? process.env.SESSION_MNEMONIC
  const webhookUrl = get('--webhook-url') ?? process.env.SESSION_WEBHOOK_URL

  if (!mnemonic) {
    throw new Error('Missing bot mnemonic. Pass --mnemonic "word word ..." or set SESSION_MNEMONIC env var.')
  }
  if (!webhookUrl) {
    throw new Error('Missing --webhook-url (where inbound Session DMs get POSTed)')
  }

  return {
    mnemonic,
    webhookUrl,
    host: get('--host') ?? '127.0.0.1',
    port: Number(get('--port') ?? '8080'),
    path: get('--path') ?? '/webhook',
    nick: get('--nick') ?? 'session-webhook-bot',
    timeoutMs: Number(get('--timeout-ms') ?? '10000'),
  }
}

function main() {
  let args: CliArgs
  try {
    args = parseArgs(process.argv.slice(2))
  } catch (err) {
    console.error(err instanceof Error ? err.message : err)
    console.error('\nUsage: bun run src/server.ts --webhook-url <url> [--mnemonic "..."] [--host 0.0.0.0] [--port 8080] [--path /webhook] [--nick MyBot]')
    process.exit(1)
  }

  const config = defaultWebhookConfig({
    callbackUrl: args.webhookUrl,
    nick: args.nick,
    path: args.path,
    timeoutMs: args.timeoutMs,
    host: args.host,
    port: args.port,
  })

  const bridge = new SessionWebhookBridge(args.mnemonic, config)
  bridge.start()
  startServer(bridge, config)
}

main()
