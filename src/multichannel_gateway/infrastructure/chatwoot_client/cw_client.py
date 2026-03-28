import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Literal, Any

import structlog
from aiohttp import ClientError, ClientResponse
from aiohttp.client_exceptions import ContentTypeError

from src.multichannel_gateway.infrastructure.session_manager import HTTPSessionManager
from src.multichannel_gateway.core.exceptions import FatalError, TransientError
from src.multichannel_gateway.core.interfaces.cw_client import IChatwootClient
from src.multichannel_gateway.infrastructure.pydantic_models import (
    ContactInfo,
    ContactSearchResult,
)

logger = structlog.get_logger(__name__)


class ChatwootClient(IChatwootClient):
    """Asynchronous client for interacting with the Chatwoot API."""

    def __init__(
        self,
        api_access_token: str,
        base_url: str,
        cw_session_manager: HTTPSessionManager,
    ):
        self.api_access_token = api_access_token
        self.base_url = base_url
        self._headers = {
            "Content-Type": "application/json",
            "api_access_token": self.api_access_token,
        }
        self._cw_sm = cw_session_manager

    async def deliver_message(
        self,
        account_id: int,
        identifier: str,
        inbox_id: int,
        content: str,
        name: str | None = None,
        email: str | None = None,
        phone_number: str | None = None,
    ) -> None:
        """Facade method to find or create a contact, ensure conversation exists,
        and send a message to that conversation.
        No value is returned. Errors are raised for non-2xx status codes.
        """

        # Step 1: Search for the contact
        found_contact = await self._search_contact(account_id, identifier)
        conversation_id: int | None

        if found_contact is None:
            # If contact does not exist, create it
            contact = await self._create_contact(
                account_id, inbox_id, identifier, name, email, phone_number
            )
            # After creating contact, we need to create a new conversation
            conversation_id = await self._create_conversation(
                account_id, contact.contact_id, contact.source_id, inbox_id
            )
        else:
            # If contact is found, try to get the conversation_id
            conversation_id = await self._get_conversation_id(
                account_id, found_contact.contact_id, inbox_id
            )
            if conversation_id is None:
                # If no conversation is found, create a new one
                conversation_id = await self._create_conversation(
                    account_id,
                    found_contact.contact_id,
                    found_contact.source_id,
                    inbox_id,
                )

        # Step 2: Create and send a new incoming message
        await self._create_message(account_id, conversation_id, "incoming", content)

    async def _search_contact(
        self, account_id: int, identifier: str
    ) -> ContactSearchResult | None:
        """Search for a contact by unique identifier. Returns the contact if found, otherwise None."""

        url = f"{self.base_url}/api/v1/accounts/{account_id}/contacts/search"
        params = {"q": identifier}

        data = await self._request(
            "GET",
            url,
            tid=identifier,
            params=params,
        )
        payload = data.get("payload", [])
        if not payload:
            return None

        contact = payload[0]
        inbox_info = (
            contact["contact_inboxes"][0]["inbox"]
            if contact.get("contact_inboxes")
            else {}
        )
        source_id = (
            contact["contact_inboxes"][0]["source_id"]
            if contact.get("contact_inboxes")
            else ""
        )

        return ContactSearchResult(
            contact_id=contact["id"],
            name=contact["name"],
            email=contact["email"],
            phone_number=contact["phone_number"],
            source_id=source_id,
            inbox_id=inbox_info.get("id", 0),
        )

    async def _get_conversation_id(
        self, account_id: int, contact_id: int, inbox_id: int
    ) -> int | None:
        """Retrieve the conversation ID for a contact in a given account.
        Returns conversation ID if found, otherwise None.
        """

        url = f"{self.base_url}/api/v1/accounts/{account_id}/contacts/{contact_id}/conversations"

        data = await self._request(
            "GET",
            url,
            tid=str(contact_id),
        )

        payload = data.get("payload", [])

        for p in payload:
            if p["inbox_id"] == inbox_id:
                return p["id"]
        return None

    async def _create_conversation(
        self, account_id: int, contact_id: int, source_id: str, inbox_id: int
    ) -> int:
        """Create a new conversation for a contact. Returns the ID of the created conversation."""

        url = f"{self.base_url}/api/v1/accounts/{account_id}/conversations"

        payload = {
            "contact_id": contact_id,
            "source_id": source_id,
            "inbox_id": inbox_id,
        }

        data = await self._request(
            "POST",
            url,
            tid=str(contact_id),
            json=payload,
        )

        return data["id"]

    async def _create_contact(
        self,
        account_id: int,
        inbox_id: int,
        tid: str,
        name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
    ) -> ContactInfo:
        """Create a new contact in Chatwoot."""

        url = f"{self.base_url}/api/v1/accounts/{account_id}/contacts"
        payload = {
            "inbox_id": inbox_id,
            "identifier": tid,
            "name": name or "",
            "email": email,
            "phone_number": phone,
        }

        data = await self._request(
            "POST",
            url,
            tid=tid,
            json=payload,
        )

        contact = data["payload"]["contact"]
        contact_inbox = data["payload"]["contact_inbox"]

        return ContactInfo(
            contact_id=contact["id"],
            email=contact["email"],
            name=contact["name"],
            phone_number=contact["phone_number"],
            identifier=contact["identifier"],
            source_id=contact_inbox["source_id"],
            inbox_id=contact_inbox["inbox"]["channel_id"],
        )

    async def _create_message(
        self,
        account_id: int,
        conversation_id: int,
        msg_type: Literal["incoming", "outgoing"],
        content: str,
    ) -> None:
        """Create a message in an existing conversation.
        No value is returned, errors are raised for non-2xx status codes.
        """

        url = f"{self.base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages"

        payload = {"message_type": msg_type, "content": content}

        await self._request(
            "POST",
            url,
            tid=str(conversation_id),
            json=payload,
        )

    @staticmethod
    async def _parse_json(resp: ClientResponse) -> dict[str, Any]:
        """Safely parse response JSON, falling back to plain text if needed."""

        try:
            return await resp.json()
        except ContentTypeError as exc:
            response_body = await resp.text()
            logger.error("Content type error", error=repr(exc), resp=response_body)
            raise FatalError(f"Chatwoot response format error: {exc}") from exc

    @staticmethod
    def _get_retry_delay_seconds(resp: ClientResponse) -> int:
        """Return retry delay from `Retry-After`, falling back to 60 seconds."""

        retry_after = resp.headers.get("Retry-After")
        if not retry_after:
            return 60

        try:
            return max(1, int(retry_after))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                delay_seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()
                return max(1, int(delay_seconds))
            except (TypeError, ValueError, OverflowError):
                logger.warning(
                    "Invalid Retry-After header from Chatwoot",
                    retry_after=retry_after,
                )
                return 60

    @staticmethod
    def _handle_response_errors(
        resp: ClientResponse, data: dict[str, Any], tid: str
    ) -> None:
        """Handle HTTP errors returned by Chatwoot API."""

        if resp.status >= 500:
            raise TransientError(f"Chatwoot server error {resp.status}: {data}")
        if resp.status == 429:
            delay_seconds = ChatwootClient._get_retry_delay_seconds(resp)
            raise TransientError(
                f"Chatwoot rate limit exceeded for {tid}: {data}",
                retry_delay_seconds=delay_seconds,
            )
        if resp.status >= 400:
            raise FatalError(f"Chatwoot API error {resp.status}: {data}")

    async def _request(
        self, method: str, url: str, *, tid: str, **kwargs: Any
    ) -> dict[str, Any]:
        """Perform a request and translate network failures."""

        try:
            async with self._cw_sm.session.request(
                method, url, headers=self._headers, **kwargs
            ) as resp:
                data = await self._parse_json(resp)
                self._handle_response_errors(resp, data, tid)
                return data
        except (ClientError, asyncio.TimeoutError) as exc:
            raise TransientError(f"Chatwoot request failed: {exc}") from exc
