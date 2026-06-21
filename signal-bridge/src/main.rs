//! signal-bridge — a thin, line-oriented bridge over [`presage`].
//!
//! It speaks newline-delimited JSON (NDJSON) so another process (here: the
//! gateway's Signal connector) can drive a real Signal account without the
//! flaky HTTP REST API in between. The same protocol is served two ways:
//!
//!   * `daemon` — over **stdin/stdout** (handy for local runs / debugging).
//!   * `serve`  — over a **TCP** connection, so the bridge can run as its own
//!                container and the gateway connects to it across the network.
//!
//! Protocol (identical for both transports):
//!   * outbound (bridge → client), one JSON object per line:
//!       {"type":"linked",...} {"type":"ready"}
//!       {"type":"message","source_uuid":..,"source_name":..,"timestamp":..,
//!        "message":..,"attachments":[{"data":<base64>,"content_type":..,
//!                                     "filename":..,"size":..}]}
//!       {"type":"queue_empty"} {"type":"send_result",..} {"type":"error",..}
//!   * inbound (client → bridge), one JSON object per line:
//!       {"recipient":"<uuid-or-service-id>","message":"hello"}
//!       {"recipient":"<uuid-or-service-id>","message":"caption",
//!        "attachments":[{"data":"<base64>","content_type":"image/png",
//!                        "filename":"pic.png"}]}
//!     `message` may be empty when `attachments` carries the whole message.
//!
//! Diagnostic logging goes to **stderr** so the protocol stream stays clean.
//!
//! Subcommands:
//!   * `link`   — link as a secondary device; emits the provisioning URL.
//!   * `whoami` — print the linked account identifiers.
//!   * `daemon` — run the protocol over stdin/stdout.
//!   * `serve`  — run the protocol over TCP (one client at a time).

use std::rc::Rc;
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result};
use base64::prelude::{Engine as _, BASE64_STANDARD};
use clap::{Parser, Subcommand};
use futures::{channel::oneshot, future, pin_mut, StreamExt};
use presage::libsignal_service::configuration::SignalServers;
use presage::libsignal_service::content::{Content, ContentBody, DataMessage};
use presage::libsignal_service::prelude::Uuid;
use presage::libsignal_service::protocol::ServiceId;
use presage::libsignal_service::sender::AttachmentSpec;
use presage::manager::Registered;
use presage::model::identity::OnNewIdentity;
use presage::model::messages::Received;
use presage::proto::AttachmentPointer;
use presage::store::Store;
use presage::Manager;
use presage_store_sqlite::SqliteStore;
use serde::Deserialize;
use serde_json::{json, Value};
use tokio::io::{AsyncBufRead, AsyncBufReadExt, AsyncWrite, AsyncWriteExt, BufReader};
use tokio::net::TcpListener;
use tokio::sync::Mutex;
use tracing::{info, warn};

/// A shared, line-buffered output sink. Both the receive task and the send
/// loop write events through it, so it is behind a mutex. `Rc` (not `Arc`)
/// because everything runs on a single-threaded `LocalSet`.
type Sink = Rc<Mutex<Box<dyn AsyncWrite + Unpin>>>;

#[derive(Parser)]
#[clap(about = "Line-oriented presage bridge (NDJSON over stdio or TCP)")]
struct Args {
    /// Path to the encrypted SQLite store that holds the linked session.
    #[clap(long, env = "SIGNAL_DB_PATH", default_value = "/data/signal.db3")]
    db_path: String,

    /// Optional passphrase encrypting the local store.
    #[clap(long, env = "SIGNAL_PASSPHRASE")]
    passphrase: Option<String>,

    /// Which Signal servers to talk to ("production" or "staging").
    #[clap(long, env = "SIGNAL_SERVERS", default_value = "production")]
    servers: SignalServers,

    #[clap(subcommand)]
    command: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// Link this bridge as a secondary device of an existing account.
    Link {
        /// Device name shown in the phone's "Linked Devices" list.
        #[clap(long, env = "SIGNAL_DEVICE_NAME", default_value = "chatwoot-gateway")]
        device_name: String,
    },
    /// Print the linked account identifiers and exit.
    Whoami,
    /// Run the NDJSON protocol over stdin/stdout.
    Daemon,
    /// Run the NDJSON protocol over a TCP socket (one client at a time).
    Serve {
        /// Address to listen on, e.g. "0.0.0.0:8080".
        #[clap(long, env = "SIGNAL_LISTEN", default_value = "0.0.0.0:8080")]
        listen: String,
    },
}

/// One outgoing send request, read as a single JSON line from the client.
#[derive(Deserialize)]
struct Outgoing {
    /// A bare UUID (ACI) or a full service-id string (e.g. "PNI:<uuid>").
    recipient: String,
    /// The text body to send. May be empty when `attachments` carries the
    /// whole message (e.g. an image with no caption).
    #[serde(default)]
    message: String,
    /// Files to attach. Each carries its bytes inline as base64 so the whole
    /// request stays a single JSON line, matching the NDJSON protocol.
    #[serde(default)]
    attachments: Vec<OutgoingAttachment>,
}

/// One outgoing attachment: the file bytes (base64) plus presentation metadata.
#[derive(Deserialize)]
struct OutgoingAttachment {
    /// base64-encoded file contents (standard alphabet, with padding).
    data: String,
    /// MIME type; defaults to `application/octet-stream` when absent.
    #[serde(default)]
    content_type: Option<String>,
    /// Original file name shown to the recipient.
    #[serde(default)]
    filename: Option<String>,
    /// Whether to mark the attachment as a voice note.
    #[serde(default)]
    voice_note: Option<bool>,
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_writer(std::io::stderr)
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();

    let args = Args::parse();

    let store = SqliteStore::open_with_passphrase(
        &args.db_path,
        args.passphrase.as_deref(),
        OnNewIdentity::Trust,
    )
    .await
    .context("failed to open signal store")?;

    // presage's Manager is not `Send`, so everything runs on a LocalSet.
    let local = tokio::task::LocalSet::new();
    local.run_until(run(args.command, args.servers, store)).await
}

async fn run<S>(command: Cmd, servers: SignalServers, store: S) -> Result<()>
where
    S: Store + Clone + 'static,
{
    match command {
        Cmd::Link { device_name } => link(store, servers, device_name).await,
        Cmd::Whoami => {
            let manager = load_registered(store).await?;
            emit(&stdout_sink(), &whoami_event(&manager)).await;
            Ok(())
        }
        Cmd::Daemon => {
            let manager = load_registered(store).await?;
            let reader = BufReader::new(tokio::io::stdin());
            session(manager, reader, stdout_sink()).await
        }
        Cmd::Serve { listen } => serve(store, &listen).await,
    }
}

/// Accept TCP clients one at a time; each connection runs a full protocol
/// session. The Signal session is only active while a client is connected,
/// so messages stay queued on Signal's servers when the gateway is away.
async fn serve<S>(store: S, listen: &str) -> Result<()>
where
    S: Store + Clone + 'static,
{
    let listener = TcpListener::bind(listen)
        .await
        .with_context(|| format!("failed to bind {listen}"))?;
    info!(listen, "signal-bridge listening");

    loop {
        let (stream, peer) = listener.accept().await.context("accept failed")?;
        info!(%peer, "client connected");
        let manager = match load_registered(store.clone()).await {
            Ok(manager) => manager,
            Err(error) => {
                warn!(%error, "cannot start session (not linked?)");
                continue;
            }
        };
        let (read_half, write_half) = stream.into_split();
        let reader = BufReader::new(read_half);
        let sink: Sink = Rc::new(Mutex::new(Box::new(write_half)));
        if let Err(error) = session(manager, reader, sink).await {
            warn!(%error, "session ended with error");
        }
        info!(%peer, "client disconnected");
    }
}

/// Link as a secondary device, emitting the provisioning URL for the caller
/// to render as a QR code (scan from Signal → Linked Devices → Link New Device).
async fn link<S>(store: S, servers: SignalServers, device_name: String) -> Result<()>
where
    S: Store,
{
    let sink = stdout_sink();
    let (tx, rx) = oneshot::channel();
    let (manager, ()) = future::join(
        Manager::link_secondary_device(store, servers, device_name, tx),
        async {
            match rx.await {
                Ok(url) => {
                    // Render a scannable QR on stderr (stdout stays clean JSON).
                    // The provisioning URL carries key material — never send it
                    // to a remote QR generator; render it locally.
                    render_qr(&url.to_string());
                    emit(&sink, &json!({"type": "link", "url": url.to_string()})).await
                }
                Err(error) => {
                    emit(
                        &sink,
                        &json!({"type": "error", "error": format!("linking cancelled: {error}")}),
                    )
                    .await
                }
            }
        },
    )
    .await;

    let manager = manager.map_err(to_anyhow).context("linking failed")?;
    emit(&stdout_sink(), &whoami_event(&manager)).await;
    Ok(())
}

/// Run one protocol session: receive on a cloned manager while the main task
/// pumps inbound command lines. Ends when the client disconnects or the
/// receive stream stops.
async fn session<S, R>(manager: Manager<S, Registered>, reader: R, sink: Sink) -> Result<()>
where
    S: Store + Clone + 'static,
    R: AsyncBufRead + Unpin,
{
    // Receiving consumes the message stream; sending needs a `&mut` handle.
    // presage supports this by cloning the manager (both share the store).
    let recv_manager = manager.clone();
    let recv_sink = sink.clone();
    let mut recv_task = tokio::task::spawn_local(async move {
        if let Err(error) = receive_loop(recv_manager, &recv_sink).await {
            emit(
                &recv_sink,
                &json!({"type": "error", "error": format!("receive loop ended: {error}")}),
            )
            .await;
        }
    });

    emit(&sink, &whoami_event(&manager)).await;
    emit(&sink, &json!({"type": "ready"})).await;

    let mut manager = manager;
    let mut lines = reader.lines();
    loop {
        tokio::select! {
            // If the receive stream dies, end the session so the client reconnects.
            _ = &mut recv_task => break,
            line = lines.next_line() => {
                let Some(line) = line? else { break };
                let line = line.trim();
                if line.is_empty() {
                    continue;
                }
                handle_command(&mut manager, &sink, line).await;
            }
        }
    }

    recv_task.abort();
    Ok(())
}

/// Parse one inbound command line and act on it, emitting a `send_result`.
async fn handle_command<S>(manager: &mut Manager<S, Registered>, sink: &Sink, line: &str)
where
    S: Store,
{
    match serde_json::from_str::<Outgoing>(line) {
        Ok(out) => match send_message(manager, &out).await {
            Ok(timestamp) => {
                emit(
                    sink,
                    &json!({"type": "send_result", "ok": true, "recipient": out.recipient, "timestamp": timestamp}),
                )
                .await
            }
            Err(error) => {
                emit(
                    sink,
                    &json!({"type": "send_result", "ok": false, "recipient": out.recipient, "error": format!("{error}")}),
                )
                .await
            }
        },
        Err(error) => {
            emit(
                sink,
                &json!({"type": "error", "error": format!("invalid command JSON: {error}")}),
            )
            .await
        }
    }
}

/// Drive the receive stream, emitting one JSON line per relevant event.
async fn receive_loop<S>(mut manager: Manager<S, Registered>, sink: &Sink) -> Result<()>
where
    S: Store,
{
    let messages = manager
        .receive_messages()
        .await
        .map_err(to_anyhow)
        .context("failed to initialize message stream")?;
    pin_mut!(messages);

    while let Some(received) = messages.next().await {
        match received {
            Received::QueueEmpty => emit(sink, &json!({"type": "queue_empty"})).await,
            Received::Contacts => {}
            Received::Content(content) => emit_incoming(&manager, sink, &content).await,
        }
    }

    Ok(())
}

/// Emit a single incoming **1:1** message. Text and/or attachments are
/// surfaced; group messages and content that carries neither text nor a
/// fetchable attachment (reactions, receipts, typing, sync, empty bodies)
/// are dropped. Attachments are downloaded from the CDN and carried inline
/// as base64, mirroring the outgoing protocol.
async fn emit_incoming<S>(manager: &Manager<S, Registered>, sink: &Sink, content: &Content)
where
    S: Store,
{
    let ContentBody::DataMessage(data) = &content.body else {
        return;
    };
    // Skip group messages — 1:1 only.
    if data.group_v2.is_some() {
        return;
    }

    let text = data.body.as_deref().unwrap_or("");
    let attachments = fetch_incoming_attachments(manager, data).await;
    if text.is_empty() && attachments.is_empty() {
        return;
    }

    let sender = &content.metadata.sender;
    let name = manager
        .store()
        .contact_by_id(sender)
        .await
        .ok()
        .flatten()
        .map(|c| c.name)
        .filter(|n| !n.is_empty());

    emit(
        sink,
        &json!({
            "type": "message",
            "source_uuid": sender.raw_uuid().to_string(),
            "source_name": name,
            "timestamp": data.timestamp,
            "message": text,
            "attachments": attachments,
        }),
    )
    .await;
}

/// Download each attachment referenced by an incoming `DataMessage` and return
/// them as JSON objects carrying the bytes inline as base64. Attachments that
/// fail to download are logged and skipped rather than dropping the message.
async fn fetch_incoming_attachments<S>(
    manager: &Manager<S, Registered>,
    data: &DataMessage,
) -> Vec<Value>
where
    S: Store,
{
    let mut out = Vec::with_capacity(data.attachments.len());
    for pointer in &data.attachments {
        match manager.get_attachment(pointer).await {
            Ok(bytes) => out.push(json!({
                "data": BASE64_STANDARD.encode(&bytes),
                "content_type": pointer.content_type,
                "filename": pointer.file_name,
                "size": pointer.size,
            })),
            Err(error) => warn!(%error, "failed to fetch incoming attachment"),
        }
    }
    out
}

/// Send a message (text and/or attachments) to a single recipient. Returns
/// the message timestamp. Attachments are uploaded to the CDN first, then
/// linked into the `DataMessage`.
async fn send_message<S>(manager: &mut Manager<S, Registered>, out: &Outgoing) -> Result<u64>
where
    S: Store,
{
    let recipient = parse_recipient(&out.recipient)?;
    let timestamp = now_millis();

    let attachments = upload_outgoing_attachments(manager, &out.attachments).await?;

    // Signal treats a missing body and an empty body differently; send `None`
    // for attachment-only messages so they don't carry a stray empty caption.
    let body = if out.message.is_empty() {
        None
    } else {
        Some(out.message.clone())
    };

    let data = DataMessage {
        body,
        timestamp: Some(timestamp),
        attachments,
        ..Default::default()
    };
    manager
        .send_message(recipient, data, timestamp)
        .await
        .map_err(to_anyhow)
        .context("failed to send message")?;
    Ok(timestamp)
}

/// Decode and upload each outgoing attachment to Signal's CDN, returning the
/// pointers to link into a `DataMessage`. An empty input is a no-op.
async fn upload_outgoing_attachments<S>(
    manager: &Manager<S, Registered>,
    attachments: &[OutgoingAttachment],
) -> Result<Vec<AttachmentPointer>>
where
    S: Store,
{
    if attachments.is_empty() {
        return Ok(Vec::new());
    }

    let mut specs = Vec::with_capacity(attachments.len());
    for attachment in attachments {
        let data = BASE64_STANDARD
            .decode(attachment.data.as_bytes())
            .context("attachment `data` is not valid base64")?;
        let spec = AttachmentSpec {
            content_type: attachment
                .content_type
                .clone()
                .unwrap_or_else(|| "application/octet-stream".to_string()),
            length: data.len(),
            file_name: attachment.filename.clone(),
            preview: None,
            voice_note: attachment.voice_note,
            borderless: None,
            width: None,
            height: None,
            caption: None,
            blur_hash: None,
        };
        specs.push((spec, data));
    }

    let mut pointers = Vec::with_capacity(specs.len());
    for result in manager
        .upload_attachments(specs)
        .await
        .map_err(to_anyhow)
        .context("failed to upload attachments")?
    {
        pointers.push(result.map_err(to_anyhow).context("attachment upload failed")?);
    }
    Ok(pointers)
}

/// Accept either a full service-id string ("PNI:<uuid>" / "<uuid>") or a bare
/// UUID, which is treated as an ACI (the common case for 1:1 replies).
fn parse_recipient(value: &str) -> Result<ServiceId> {
    if let Some(service_id) = ServiceId::parse_from_service_id_string(value) {
        return Ok(service_id);
    }
    let uuid = Uuid::parse_str(value)
        .with_context(|| format!("recipient is not a valid ServiceId or UUID: {value}"))?;
    Ok(ServiceId::Aci(uuid.into()))
}

async fn load_registered<S: Store>(store: S) -> Result<Manager<S, Registered>> {
    Manager::load_registered(store)
        .await
        .map_err(to_anyhow)
        .context("not linked yet — run `link` first")
}

fn whoami_event<S: Store>(manager: &Manager<S, Registered>) -> Value {
    let data = manager.registration_data();
    json!({
        "type": "linked",
        "number": data.phone_number.to_string(),
        "service_ids": data.service_ids.to_string(),
    })
}

/// Render the provisioning URL as a QR code on stderr so it can be scanned
/// from the Signal app (Settings → Linked Devices → Link New Device).
fn render_qr(url: &str) {
    match qr2term::generate_qr_string(url) {
        Ok(qr) => eprintln!("\nScan this QR code from Signal → Linked Devices:\n\n{qr}"),
        Err(error) => eprintln!("failed to render QR code ({error}); use the URL above"),
    }
}

fn stdout_sink() -> Sink {
    Rc::new(Mutex::new(Box::new(tokio::io::stdout())))
}

fn now_millis() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("system clock before unix epoch")
        .as_millis() as u64
}

/// Write a single JSON event as one line, atomically (per write the sink is
/// locked, so concurrent emits never interleave within a line).
async fn emit(sink: &Sink, value: &Value) {
    let mut line = value.to_string();
    line.push('\n');
    let mut out = sink.lock().await;
    let _ = out.write_all(line.as_bytes()).await;
    let _ = out.flush().await;
}

/// presage's `Error<S::Error>` is generic; collapse it to an `anyhow` error
/// via its `Display` impl so callers don't need its trait bounds.
fn to_anyhow<E: std::fmt::Display>(error: E) -> anyhow::Error {
    anyhow::anyhow!("{error}")
}
