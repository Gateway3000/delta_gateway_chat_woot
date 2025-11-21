import structlog
from fastapi import HTTPException, APIRouter, status
from fastapi.requests import Request
from fastapi.responses import Response

from app.di import gateways
from core.exceptions import (
    ConnectorNotFoundError,
    WrongUpdateTypeError,
    IdempotencyKeyAlreadyProcessedError,
)

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.post("/ingest/incoming/{channel}/{connector_id}/webhook")
async def to_chatwoot(channel: str, connector_id: str, request: Request) -> Response:
    """An endpoint for handling Channel -> Chatwoot webhooks."""

    raw_data = await request.json()
    try:
        gateway = gateways.get_gateway(channel)
        await gateway.process_inbound(raw_data, connector_id)
    except ConnectorNotFoundError as e:
        logger.error("ConnectorNotFoundError", error=repr(e), raw_data=raw_data)
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Unknown connector_id"
        ) from e
    except WrongUpdateTypeError as e:
        logger.error("WrongUpdateTypeError", error=repr(e), raw_data=raw_data)
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Wrong update type"
        ) from e
    except IdempotencyKeyAlreadyProcessedError as e:
        logger.info(
            "IdempotencyKeyAlreadyProcessedError", error=repr(e), raw_data=raw_data
        )
        return Response(status_code=status.HTTP_200_OK)
    logger.debug("Inbound webhook processed successfully")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/ingest/outgoing/{channel}/{cw_account_id}/webhook")
async def from_chatwoot(channel: str, cw_account_id: str, request: Request) -> Response:
    """An endpoint for handling Chatwoot -> Channel webhooks."""

    raw_data = await request.json()
    if raw_data.get("message_type") == "outgoing":
        try:
            gateway = gateways.get_gateway(channel)
            await gateway.process_outbound(raw_data, cw_account_id)
        except IdempotencyKeyAlreadyProcessedError as e:
            logger.info(
                "IdempotencyKeyAlreadyProcessedError", error=repr(e), raw_data=raw_data
            )
            return Response(status_code=status.HTTP_200_OK)
    logger.debug("Outbound webhook processed successfully")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
