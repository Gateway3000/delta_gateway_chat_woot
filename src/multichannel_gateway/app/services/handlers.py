from typing import Any

import structlog
from fastapi import HTTPException, status
from fastapi.responses import Response
from opentelemetry.trace import Span, Tracer, get_tracer

from src.multichannel_gateway.core import (
    ConnectorNotFoundError,
    IdempotencyKeyAlreadyProcessedError,
    TransientError,
    WrongUpdateTypeError,
)
from src.multichannel_gateway.core.interfaces.envelope_factory import IEnvelopeFactory
from src.multichannel_gateway.infrastructure.telemetry import (
    build_webhook_attributes,
    mark_span_error,
    mark_span_ok,
    set_span_attributes,
)

logger = structlog.get_logger(__name__)
tracer: Tracer = get_tracer(__name__)


async def handle_channel_payload(
    channel: str, connector_id: str, payload: dict[str, Any]
) -> Response | None:
    from src.multichannel_gateway.app.wiring import channel_to_chatwoot_orchestrator

    with tracer.start_as_current_span("webhook.channel_to_chatwoot") as span:
        set_span_attributes(
            span,
            build_webhook_attributes(channel, connector_id=connector_id),
        )

        payload["channel"] = channel
        payload["connector_id"] = connector_id

        try:
            await channel_to_chatwoot_orchestrator.process(channel, payload)
            mark_span_ok(span)
        except Exception as e:
            if response := _handle_exceptions(e, span, payload):
                return response
            raise
        return None


async def handle_chatwoot_payload(
    channel: str, cw_account_id: str, payload: dict[str, Any]
) -> Response | None:
    from src.multichannel_gateway.app.wiring import alias_store, registry, settings

    with tracer.start_as_current_span("webhook.chatwoot_to_channel") as span:
        set_span_attributes(
            span,
            build_webhook_attributes(channel, cw_account_id=cw_account_id),
        )

        if payload.get("message_type") == "outgoing":
            try:
                identifier = payload["conversation"]["meta"]["sender"]["identifier"]

                if settings.anonymize_users:
                    # Identifier is an opaque alias — resolve it back to real_id.
                    # Channel comes from the webhook URL (no prefix to detect from).
                    real_id = await alias_store.resolve_alias(identifier)
                    if real_id is None:
                        raise ConnectorNotFoundError(
                            f"Unknown alias: {identifier}"
                        )
                    payload["conversation"]["meta"]["sender"]["identifier"] = real_id
                    target_channel = channel
                else:
                    # Contact identifiers are channel-prefixed (e.g. "simplex_3").
                    # Route by that prefix rather than the channel in the webhook
                    # URL, so a single Chatwoot account webhook serves every channel
                    # and replies never land on the wrong transport.
                    target_channel = _resolve_outgoing_channel(
                        identifier, channel, registry
                    )
                    payload["conversation"]["meta"]["sender"]["identifier"] = (
                        IEnvelopeFactory._strip_channel_prefix(identifier, target_channel)
                    )

                channel_ = registry.get_channel(target_channel)
                await channel_.publish_chatwoot_message(payload, cw_account_id)
                mark_span_ok(span)
            except Exception as e:
                if response := _handle_exceptions(e, span, payload):
                    return response
                raise
        else:
            set_span_attributes(
                span,
                {"chatwoot.message_type": payload.get("message_type")},
            )
            mark_span_ok(span)

        logger.debug(f"Chatwoot->{channel.capitalize()} webhook processed successfully")
        return None


def _resolve_outgoing_channel(
    identifier: Any, url_channel: str, registry: Any
) -> str:
    """Pick the channel from the identifier's prefix, else the URL channel.

    Inbound, the orchestrator prefixes every contact identifier with its
    channel ("<channel>_<id>"). Outbound, Chatwoot account webhooks fire for
    all channels regardless of the URL, so we trust the prefix to dispatch to
    the right transport. Falls back to the URL channel for unprefixed ids.
    """
    if isinstance(identifier, str):
        for name in registry.channel_names:
            if identifier.startswith(f"{name}_"):
                return name
    return url_channel


def _handle_exceptions(
    exc: Exception, span: Span, raw_data: dict[str, object]
) -> Response | None:
    if isinstance(exc, ConnectorNotFoundError):
        mark_span_error(span, exc)
        logger.error("ConnectorNotFoundError", error=repr(exc), raw_data=raw_data)
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Unknown connector_id"
        ) from exc

    if isinstance(exc, WrongUpdateTypeError):
        mark_span_error(span, exc)
        logger.warning("WrongUpdateTypeError", error=repr(exc), raw_data=raw_data)
        raise HTTPException(
            status.HTTP_204_NO_CONTENT, detail="Wrong update type"
        ) from exc

    if isinstance(exc, IdempotencyKeyAlreadyProcessedError):
        mark_span_ok(span)
        logger.info(
            "IdempotencyKeyAlreadyProcessedError",
            error=repr(exc),
            raw_data=raw_data,
        )
        return Response(status_code=status.HTTP_200_OK)

    if isinstance(exc, TransientError):
        mark_span_error(span, exc)
        logger.error(
            "TransientError while processing webhook",
            error=repr(exc),
            raw_data=raw_data,
            retry_after_seconds=exc.retry_delay_seconds,
        )
        return Response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={"Retry-After": str(exc.retry_delay_seconds)},
        )

    mark_span_error(span, exc)
    return None
