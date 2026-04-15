import structlog
from fastapi import HTTPException, APIRouter, status
from fastapi.requests import Request
from fastapi.responses import Response
from opentelemetry.trace import Span, Tracer, get_tracer

from src.multichannel_gateway.app.wiring import registry
from src.multichannel_gateway.core import (
    ConnectorNotFoundError,
    IdempotencyKeyAlreadyProcessedError,
    TransientError,
    WrongUpdateTypeError,
)
from src.multichannel_gateway.infrastructure.telemetry import (
    build_webhook_attributes,
    mark_span_error,
    mark_span_ok,
    set_span_attributes,
)

logger = structlog.get_logger(__name__)
router = APIRouter()

tracer: Tracer = get_tracer(__name__)


@router.post("/ingest/incoming/{channel}/{connector_id}/webhook")
async def to_chatwoot(channel: str, connector_id: str, request: Request) -> Response:
    """An endpoint for handling Channel -> Chatwoot webhooks."""

    with tracer.start_as_current_span("webhook.incoming") as span:
        set_span_attributes(
            span,
            build_webhook_attributes(channel, connector_id=connector_id),
        )
        raw_data = await request.json()
        raw_data["channel"] = channel
        raw_data["connector_id"] = connector_id
        try:
            channel_ = registry.get_channel(channel)
            await channel_.process_inbound(raw_data)
            mark_span_ok(span)
        except Exception as e:
            if response := _handle_exceptions(e, span, raw_data):
                return response
            raise
        logger.debug("Inbound webhook processed successfully")
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/ingest/outgoing/{channel}/{cw_account_id}/webhook")
async def from_chatwoot(channel: str, cw_account_id: str, request: Request) -> Response:
    """An endpoint for handling Chatwoot -> Channel webhooks."""

    with tracer.start_as_current_span("webhook.outgoing") as span:
        set_span_attributes(
            span,
            build_webhook_attributes(channel, cw_account_id=cw_account_id),
        )
        raw_data = await request.json()
        if raw_data.get("message_type") == "outgoing":
            try:
                channel_ = registry.get_channel(channel)
                await channel_.process_outbound(raw_data, cw_account_id)
                mark_span_ok(span)
            except Exception as e:
                if response := _handle_exceptions(e, span, raw_data):
                    return response
                raise
        else:
            set_span_attributes(
                span,
                {"chatwoot.message_type": raw_data.get("message_type")},
            )
            mark_span_ok(span)
        logger.debug("Outbound webhook processed successfully")
        return Response(status_code=status.HTTP_204_NO_CONTENT)


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
        logger.error("WrongUpdateTypeError", error=repr(exc), raw_data=raw_data)
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Wrong update type"
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
