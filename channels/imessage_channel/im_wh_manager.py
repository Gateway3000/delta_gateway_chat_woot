import structlog

from channels.imessage_channel.im_bot_manager import IMessageBotManager
from channels.imessage_channel.plugin_settings import IMessageSettings

logger = structlog.get_logger(__name__)


class IMessageWebhookManager:
    """Surfaces webhook setup instructions for BlueBubbles connectors.

    Unlike Telegram's `set_webhook` / `delete_webhook` API calls, BlueBubbles
    has no endpoint to register a webhook programmatically — it's configured
    once, manually, in the Server app's "API & Webhooks" UI on the Mac
    itself. So this class can't *set* anything; it can only make the
    required URL loud and obvious at boot so the operator doesn't have to
    go hunting for it, and fail fast if the settings needed to build that
    URL are missing.
    """

    def __init__(
        self,
        wh_domain: str | None,
        bots_config_connector_ids: list[str],
        settings: IMessageSettings,
        bot_manager: IMessageBotManager,
    ):
        self._wh_domain = wh_domain
        self._connector_ids = bots_config_connector_ids
        self._settings = settings
        self._bots = bot_manager

    async def set_wh(self) -> None:
        if not self._wh_domain:
            raise ValueError("WH_DOMAIN must be set")

        for connector_id in self._connector_ids:
            path = self._settings.webhook_path_template.format(
                connector_id=connector_id
            )
            webhook_url = f"{self._wh_domain}{path}"
            logger.warning(
                "BlueBubbles webhook must be configured manually",
                connector_id=connector_id,
                webhook_url=webhook_url,
                instructions=(
                    "In the BlueBubbles Server app: API & Webhooks -> Manage "
                    "-> Add Webhook. Paste the URL above and subscribe to "
                    "the 'New Message' event."
                ),
            )
