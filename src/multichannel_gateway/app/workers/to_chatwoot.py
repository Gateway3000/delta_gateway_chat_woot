from typing import Any

import structlog
from opentelemetry.trace import SpanKind

from src.multichannel_gateway.app.workers.base import BaseWorker
from src.multichannel_gateway.core.interfaces import IChatwootClient
from src.multichannel_gateway.infrastructure import PGMessageQueue
from src.multichannel_gateway.infrastructure.telemetry import (
    get_tracer,
    mark_span_ok,
    set_span_attributes,
)

logger = structlog.get_logger(__name__)
tracer = get_tracer(__name__)


class ChannelToChatwootWorker(BaseWorker):
    def __init__(
        self,
        mq: PGMessageQueue,
        cw_client: IChatwootClient,
        queue_name: str,
    ):
        super().__init__(mq, queue_name)
        self._mq = mq
        self._queue_name = queue_name
        self._cwc = cw_client

    async def _handle_message(self, payload: dict[str, Any]) -> None:
        """
        Contains the logic for processing messages from Gateway to Chatwoot.

        Error handling:
          - Raise `TransientError` for temporary issues, including HTTP 429.
          - Raise `FatalError` for non-retryable 4xx responses.
        """
        with tracer.start_as_current_span(
            "worker.channel_to_chatwoot.deliver", kind=SpanKind.INTERNAL
        ) as span:
            channel = payload["channel"]
            end_user_id = payload["sender"]["external_id"]
            name = payload["sender"].get("name")
            message_text = payload["payload"].get("text") or ""
            attachments = payload["payload"].get("attachments", [])
            connector_id = payload["connector_id"]
            cw_account_id = payload["cw_account_id"]
            cw_inbox_id = payload["cw_inbox_id"]

            set_span_attributes(
                span,
                {
                    "channel": channel,
                    "connector_id": connector_id,
                    "cw.account_id": cw_account_id,
                    "cw.inbox_id": cw_inbox_id,
                    "enduser.id": end_user_id,
                    "message.attachments_count": len(attachments),
                },
            )

            if message_text or attachments:
                await self._cwc.deliver_channel_to_chatwoot_message(
                    account_id=int(cw_account_id),
                    end_user_id=str(end_user_id),
                    inbox_id=int(cw_inbox_id),
                    content=message_text,
                    name=name,
                    attachments=attachments or None,
                )
            else:
                logger.warning(
                    "Skipping empty message after failed attachments",
                    sender_id=str(end_user_id),
                )
            mark_span_ok(span)
            logger.debug(
                "Channel message delivered to Chatwoot",
                channel=channel,
                connector_id=connector_id,
                cw_account_id=cw_account_id,
                enduser_id=end_user_id,
            )
