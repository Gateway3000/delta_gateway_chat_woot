import base64
from typing import Any

import aiohttp
import structlog

logger = structlog.get_logger(__name__)

_FILE_TYPE = {
    "image": "image",
    "video": "video",
    "audio": "audio",
    "sticker": "image",
}


async def prepare_whatsapp_to_chatwoot_attachments(
    payload: dict[str, Any],
    sidecar_token: str = "",
    max_mb: int = 40,
) -> dict[str, Any]:
    """Download sidecar-hosted media and convert to base64 Chatwoot attachments.

    Mirrors the Telegram channel's attachment preparation step. Mutates and
    returns the payload dict with payload["attachments"] replaced.
    """
    raw = payload.get("attachments") or []
    if not raw:
        return payload

    headers = {"Authorization": f"Bearer {sidecar_token}"} if sidecar_token else {}
    prepared: list[dict[str, Any]] = []
    limit = max_mb * 1024 * 1024

    async with aiohttp.ClientSession(headers=headers) as session:
        for att in raw:
            url = att.get("url")
            if not url:
                continue
            try:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.warning(
                            "media fetch failed", status=resp.status, url=url
                        )
                        continue
                    data = await resp.read()
                    if len(data) > limit:
                        logger.warning("media too large, skipping", size=len(data))
                        continue
                    mime = att.get("mimetype") or resp.headers.get(
                        "Content-Type", "application/octet-stream"
                    )
            except Exception as e:  # noqa: BLE001
                logger.error("media download error", error=str(e), url=url)
                continue

            prepared.append(
                {
                    "kind": "base64",
                    "filename": att.get("filename") or att.get("id") or "file",
                    "mime_type": mime,
                    "file_type": _FILE_TYPE.get(att.get("type", ""), "file"),
                    "data": base64.b64encode(data).decode("ascii"),
                    "data_encoding": "base64",
                }
            )

    payload["attachments"] = prepared
    return payload
