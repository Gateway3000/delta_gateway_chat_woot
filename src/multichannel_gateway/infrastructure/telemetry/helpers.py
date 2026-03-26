from typing import Any

from opentelemetry.trace import Span, Status, StatusCode


def set_span_attributes(span: Span, attributes: dict[str, Any]) -> None:
    for key, value in attributes.items():
        if value is None:
            continue
        if isinstance(value, bool | str | bytes | int | float):
            span.set_attribute(key, value)
            continue
        span.set_attribute(key, str(value))


def mark_span_ok(span: Span) -> None:
    span.set_status(Status(StatusCode.OK))


def mark_span_error(span: Span, exc: Exception) -> None:
    span.record_exception(exc)
    span.set_status(Status(StatusCode.ERROR, str(exc)))


def build_worker_message_attributes(
    worker_name: str,
    queue_name: str,
    msg_id: int,
    attempts: int,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attributes: dict[str, Any] = {
        "messaging.system": "pgmq",
        "messaging.destination.name": queue_name,
        "messaging.operation": "process",
        "messaging.message.id": msg_id,
        "messaging.message.retry_count": attempts,
        "worker.name": worker_name,
    }
    if payload is None:
        return attributes

    attributes.update(
        {
            "messaging.message.channel": payload.get("channel"),
            "messaging.message.connector_id": payload.get("connector_id"),
            "messaging.message.cw_account_id": payload.get("cw_account_id"),
        }
    )

    sender = payload.get("sender")
    if isinstance(sender, dict):
        attributes["enduser.id"] = sender.get("external_id")

    return attributes


def build_webhook_attributes(
    channel: str,
    *,
    connector_id: str | None = None,
    cw_account_id: str | None = None,
) -> dict[str, Any]:
    return {
        "channel": channel,
        "connector_id": connector_id,
        "cw.account_id": cw_account_id,
    }
