from typing import Any

import structlog
from opentelemetry.trace import SpanKind

from src.multichannel_gateway.app import Settings
from src.multichannel_gateway.app.workers.base import BaseWorker
from src.multichannel_gateway.core import generate_username
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
        settings: Settings,
        mq: PGMessageQueue,
        cw_client: IChatwootClient,
        queue_name: str,
    ):
        super().__init__(mq, queue_name)
        self.settings = settings
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
            "incoming_worker.deliver_to_chatwoot", kind=SpanKind.INTERNAL
        ) as span:
            name = generate_username()[0]
            if not self.settings.anonymize_users and payload["sender"]["name"]:
                name = payload["sender"]["name"]

            channel = payload["channel"]
            tid = payload["sender"]["external_id"]
            msg = payload["payload"].get("text") or ""
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
                    "enduser.id": tid,
                    "message.attachments_count": len(attachments),
                },
            )

            if msg or attachments:
                await self._cwc.deliver_message(
                    account_id=int(cw_account_id),
                    identifier=str(tid),
                    inbox_id=int(cw_inbox_id),
                    content=msg,
                    name=name,
                    attachments=attachments or None,
                )
            else:
                logger.warning(
                    "Skipping empty message after failed attachments",
                    sender_id=str(tid),
                )
            mark_span_ok(span)
            logger.debug(
                "Incoming message delivered to Chatwoot",
                channel=channel,
                connector_id=connector_id,
                cw_account_id=cw_account_id,
                enduser_id=tid,
            )
