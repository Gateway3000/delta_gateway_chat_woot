from datetime import datetime

from fastapi import HTTPException, APIRouter
from pydantic import BaseModel, Field
from starlette import status
from starlette.requests import Request
from starlette.responses import Response

from app.di import tg_gateway
from core.exceptions import ConnectorNotFoundError, WrongUpdateTypeError

router = APIRouter()


class OutboundPayload(BaseModel):
    id: str
    channel: str
    connector_id: str
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
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Unknown connector_id"
        ) from e
    except WrongUpdateTypeError as e:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Wrong update type"
        ) from e

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/ingest/outgoing/{cw_account_id}/webhook")
async def chatwoot_webhook(cw_account_id: str, request: OutboundPayload) -> Response:
    raw_data = request.model_dump(by_alias=True)
    await tg_gateway.process_outbound(cw_account_id, raw_data)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
