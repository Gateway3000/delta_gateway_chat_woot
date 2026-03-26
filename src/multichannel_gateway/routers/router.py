import structlog
from fastapi import HTTPException, APIRouter, status
from fastapi.requests import Request
from fastapi.responses import Response
from opentelemetry.trace import Tracer, get_tracer

from src.multichannel_gateway.app.di import registry
from src.multichannel_gateway.core.exceptions import (
    ConnectorNotFoundError,
    WrongUpdateTypeError,
    IdempotencyKeyAlreadyProcessedError,
)
from src.multichannel_gateway.infrastructure.telemetry.helpers import (
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
        try:
            gateway = registry.get_gateway(channel)
            await gateway.process_inbound(raw_data, connector_id)
            mark_span_ok(span)

        except ConnectorNotFoundError as e:
            mark_span_error(span, e)
            logger.error("ConnectorNotFoundError", error=repr(e), raw_data=raw_data)
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Unknown connector_id"
            ) from e
        except WrongUpdateTypeError as e:
            mark_span_error(span, e)
            logger.error("WrongUpdateTypeError", error=repr(e), raw_data=raw_data)
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Wrong update type"
            ) from e
        except IdempotencyKeyAlreadyProcessedError as e:
            mark_span_ok(span)
            logger.info(
                "IdempotencyKeyAlreadyProcessedError", error=repr(e), raw_data=raw_data
            )
            return Response(status_code=status.HTTP_200_OK)
        except Exception as e:
            mark_span_error(span, e)
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
                gateway = registry.get_gateway(channel)
                await gateway.process_outbound(raw_data, cw_account_id)
                mark_span_ok(span)

            except IdempotencyKeyAlreadyProcessedError as e:
                mark_span_ok(span)
                logger.info(
                    "IdempotencyKeyAlreadyProcessedError",
                    error=repr(e),
                    raw_data=raw_data,
                )
                return Response(status_code=status.HTTP_200_OK)
            except Exception as e:
                mark_span_error(span, e)
                raise
        else:
            span.set_attribute("chatwoot.message_type", raw_data.get("message_type"))
            mark_span_ok(span)
        logger.debug("Outbound webhook processed successfully")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
