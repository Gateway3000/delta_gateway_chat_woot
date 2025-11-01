from datetime import datetime

import structlog
from fastapi import HTTPException, APIRouter, status
from fastapi.requests import Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, ConfigDict

from app.di import tg_gateway
from core.exceptions import ConnectorNotFoundError, WrongUpdateTypeError

logger = structlog.get_logger(__name__)
router = APIRouter()


class OutboundPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, coerce_numbers_to_str=True)

    channel: str
    connector_id: str
    inbox_id: str
    cw_account_id: str
    message_id: str
    from_: dict[str, str] = Field(alias="from")
    text: str
    ts: datetime


@router.post("/ingest/incoming/tg/{connector_id}/webhook")
async def telegram_webhook(connector_id: str, request: Request) -> Response:
    """FastAPI endpoint for handling Telegram webhooks."""

    raw_data = await request.json()

    try:
        await tg_gateway.process_inbound(connector_id, raw_data)
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
    logger.debug("Inbound webhook processed successfully")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/ingest/outgoing/{cw_account_id}/webhook")
async def chatwoot_webhook(cw_account_id: str, request: Request) -> Response:
    """FastAPI endpoint for handling Chatwoot webhooks."""

    raw_data = await request.json()
    if raw_data.get("message_type") == "outgoing":
        # noinspection PyArgumentList
        payload = OutboundPayload(
            channel="telegram",
            connector_id="",
            inbox_id=raw_data["inbox"]["id"],
            cw_account_id=cw_account_id,
            message_id=raw_data["conversation"]["messages"][0]["id"],
            from_={"id": raw_data["conversation"]["meta"]["sender"]["identifier"]},
            text=raw_data.get("content"),
            ts=float(datetime.now().timestamp()),
        )

        await tg_gateway.process_outbound(payload.model_dump(by_alias=True))
    logger.debug("Outbound webhook processed successfully")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
