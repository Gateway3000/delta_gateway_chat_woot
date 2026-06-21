from fastapi import APIRouter, status
from fastapi.requests import Request
from fastapi.responses import Response

from src.multichannel_gateway.app.services.handlers import (
    handle_channel_payload,
    handle_chatwoot_payload,
)

router = APIRouter()


@router.get("/health")
async def health() -> Response:
    return Response(status_code=status.HTTP_200_OK)


@router.get("/deltachat/{connector_id}/secure-join-qr.svg")
async def deltachat_secure_join_qr(connector_id: str) -> Response:
    from src.multichannel_gateway.app.wiring import registry

    channel = registry.get_channel("delta_chat")
    get_qr = getattr(channel, "get_secure_join_qr_svg", None)
    if get_qr is None:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    svg = await get_qr(connector_id)
    return Response(content=svg, media_type="image/svg+xml")


@router.post("/ingest/incoming/{channel}/{connector_id}/webhook")
async def to_chatwoot(channel: str, connector_id: str, request: Request) -> Response:
    """An endpoint for handling Channel -> Chatwoot webhooks."""
    raw_data = await request.json()
    if response := await handle_channel_payload(channel, connector_id, raw_data):
        return response
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/messages/inbound")
async def inbound_message(request: Request) -> Response:
    raw_data = await request.json()
    channel = str(raw_data.get("channel") or "delta_chat")
    connector_id = str(raw_data["connector_id"])
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


@router.post("/messages/outbound")
async def outbound_message(request: Request) -> Response:
    raw_data = await request.json()
    channel = str(raw_data.get("channel") or "delta_chat")
    cw_account_id = str(raw_data["cw_account_id"])
    if response := await handle_chatwoot_payload(channel, cw_account_id, raw_data):
        return response
    return Response(status_code=status.HTTP_204_NO_CONTENT)
