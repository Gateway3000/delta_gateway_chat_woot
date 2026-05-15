from fastapi import APIRouter, status
from fastapi.requests import Request
from fastapi.responses import Response

from src.multichannel_gateway.app.services.handlers import (
    handle_channel_payload,
    handle_chatwoot_payload,
)

router = APIRouter()


@router.post("/ingest/incoming/{channel}/{connector_id}/webhook")
async def to_chatwoot(channel: str, connector_id: str, request: Request) -> Response:
    """An endpoint for handling Channel -> Chatwoot webhooks."""
    raw_data = await request.json()
    if response := await handle_channel_payload(channel, connector_id, raw_data):
        return response
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/ingest/outgoing/{channel}/{cw_account_id}/webhook")
async def from_chatwoot(channel: str, cw_account_id: str, request: Request) -> Response:
    """An endpoint for handling Chatwoot -> Channel webhooks."""
    raw_data = await request.json()
    if response := await handle_chatwoot_payload(channel, cw_account_id, raw_data):
        return response
    return Response(status_code=status.HTTP_204_NO_CONTENT)
