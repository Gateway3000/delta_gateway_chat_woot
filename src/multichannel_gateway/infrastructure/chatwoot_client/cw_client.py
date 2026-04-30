import mimetypes
import os
from typing import Literal, Any

import aiohttp
import structlog
from aiohttp import ClientError, ClientResponse
from aiohttp.client_exceptions import ContentTypeError
from pydantic import TypeAdapter

from src.multichannel_gateway.core.attachment_models import (
    ChatwootAttachment,
    LocalFileAttachment,
    UploadedAttachment,
)
from src.multichannel_gateway.core.exceptions import FatalError, TransientError
from src.multichannel_gateway.core.interfaces.cw_client import IChatwootClient
from src.multichannel_gateway.infrastructure.provider_models import (
    ContactInfo,
    ContactSearchResult,
)
from src.multichannel_gateway.infrastructure.session_manager import HTTPSessionManager

logger = structlog.get_logger(__name__)
attachments_adapter = TypeAdapter(list[ChatwootAttachment])


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

    async def deliver_channel_to_chatwoot_message(
        self,
        account_id: int,
        end_user_id: str,
        inbox_id: int,
        content: str,
        name: str | None = None,
        email: str | None = None,
        phone_number: str | None = None,
        attachments: list[ChatwootAttachment] | None = None,
    ) -> None:
        """Facade method to find or create a contact, ensure conversation exists,
        and deliver a Channel -> Chatwoot message into that conversation.
        No value is returned. Errors are raised for non-2xx status codes.
        """

        # Step 1: Search for the contact
        found_contact = await self._search_contact(account_id, end_user_id)
        conversation_id: int | None

        if found_contact is None:
            # If contact does not exist, create it
            contact = await self._create_contact(
                account_id, inbox_id, end_user_id, name, email, phone_number
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

        normalized_attachments = self._normalize_attachments(attachments)

        try:
            uploaded_attachments = await self._upload_message_attachments(
                account_id, normalized_attachments
            )

            # Step 2: Create and send a new incoming message
            await self._create_message(
                account_id,
                conversation_id,
                "incoming",
                content,
                attachments=uploaded_attachments,
            )
        except FatalError:
            logger.debug(
                "Cleaning up temp attachments after fatal Chatwoot delivery error",
                account_id=account_id,
                end_user_id=end_user_id,
                attachments_count=len(normalized_attachments),
            )
            self._cleanup_temp_attachments(normalized_attachments)
            raise
        else:
            logger.debug(
                "Cleaning up temp attachments after successful Chatwoot delivery",
                account_id=account_id,
                end_user_id=end_user_id,
                attachments_count=len(normalized_attachments),
            )
            self._cleanup_temp_attachments(normalized_attachments)

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
        chatwoot_message_type: Literal["incoming", "outgoing"],
        content: str,
        attachments: list[str] | None = None,
    ) -> None:
        """Create a message in an existing conversation.
        No value is returned, errors are raised for non-2xx status codes.
        """

        url = f"{self.base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages"

        payload: dict[str, Any] = {
            "message_type": chatwoot_message_type,
            "content": content,
        }
        if attachments:
            payload["attachments"] = attachments[:15]

        await self._request(
            "POST",
            url,
            tid=str(conversation_id),
            json=payload,
        )

    async def _upload_message_attachments(
        self,
        account_id: int,
        attachments: list[ChatwootAttachment] | None,
    ) -> list[str]:
        if not attachments:
            return []

        signed_ids: list[str] = []
        for attachment in attachments:
            if isinstance(attachment, UploadedAttachment):
                signed_ids.append(attachment.signed_id)
                continue

            upload_result = await self._upload_file(
                account_id,
                str(attachment.temp_file_path),
                attachment.filename,
                attachment.mime_type,
            )
            if upload_result and upload_result.get("signed_id"):
                logger.debug(
                    "Chatwoot attachment uploaded",
                    account_id=account_id,
                    filename=attachment.filename,
                    temp_file_path=str(attachment.temp_file_path),
                    signed_id=str(upload_result["signed_id"]),
                )
                signed_ids.append(str(upload_result["signed_id"]))

        return signed_ids

    @staticmethod
    def _cleanup_temp_attachments(attachments: list[ChatwootAttachment] | None) -> None:
        if not attachments:
            return

        for attachment in attachments:
            if isinstance(attachment, LocalFileAttachment) and os.path.exists(
                attachment.temp_file_path
            ):
                logger.debug(
                    "Cleaning up Chatwoot temp attachment",
                    filename=attachment.filename,
                    temp_file_path=str(attachment.temp_file_path),
                )
                os.remove(attachment.temp_file_path)

    @staticmethod
    def _normalize_attachments(
        attachments: list[ChatwootAttachment] | None,
    ) -> list[ChatwootAttachment]:
        return attachments_adapter.validate_python(attachments) if attachments else []

    async def _upload_file(
        self,
        account_id: int,
        temp_file_path: str,
        filename: str,
        mime_type: str,
    ) -> dict[str, Any] | None:
        """Upload a file to Chatwoot and return metadata needed for message attachments."""
        if not os.path.exists(temp_file_path):
            logger.error("Upload file not found", path=temp_file_path)
            return None

        resolved_mime_type = mime_type
        if not resolved_mime_type or "/" not in resolved_mime_type:
            guessed_type, _ = mimetypes.guess_type(filename)
            resolved_mime_type = guessed_type or "application/octet-stream"

        url = f"{self.base_url}/api/v1/accounts/{account_id}/upload"
        headers = {
            key: value
            for key, value in self._headers.items()
            if key.lower() != "content-type"
        }

        with open(temp_file_path, "rb") as file:
            file_content = file.read()

        data = aiohttp.FormData()
        data.add_field(
            name="attachment",
            value=file_content,
            filename=filename,
            content_type=resolved_mime_type,
        )

        try:
            async with self._cw_sm.session.post(
                url, headers=headers, data=data
            ) as resp:
                response_data = await self._parse_json(resp)
                self._handle_response_errors(resp, response_data, filename)
        except (ClientError, TimeoutError) as exc:
            logger.error(
                "Chatwoot attachment upload transient error",
                account_id=account_id,
                filename=filename,
                temp_file_path=temp_file_path,
                error=repr(exc),
            )
            raise TransientError(f"Chatwoot upload failed: {exc}") from exc

        file_url = response_data.get("file_url")
        if not file_url:
            logger.error("Upload response missing file_url", response=response_data)
            return None

        signed_id = response_data.get("signed_id")
        if not signed_id and "redirect/" in file_url:
            signed_id = file_url.split("redirect/")[1].rsplit("/", 1)[0]
        if not signed_id:
            logger.error("Upload response missing signed_id", response=response_data)
            return None

        return {
            "signed_id": signed_id,
            "file_url": file_url,
            "file_type": response_data.get("file_type", resolved_mime_type),
            "file_size": response_data.get("file_size"),
        }

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
        except (TypeError, ValueError):
            logger.warning(
                "Invalid Retry-After header from Chatwoot",
                retry_after=retry_after,
            )
            return 60

    def _handle_response_errors(
        self, resp: ClientResponse, data: dict[str, Any], tid: str
    ) -> None:
        """Handle HTTP errors returned by Chatwoot API."""

        if resp.status >= 500:
            logger.error(
                "Chatwoot server error response",
                status_code=resp.status,
                tid=tid,
                response=data,
            )
            raise TransientError(f"Chatwoot server error {resp.status}: {data}")
        if resp.status == 429:
            delay_seconds = self._get_retry_delay_seconds(resp)
            logger.error(
                "Chatwoot rate limit response",
                status_code=resp.status,
                tid=tid,
                retry_delay_seconds=delay_seconds,
                response=data,
            )
            raise TransientError(
                f"Chatwoot rate limit exceeded for {tid}: {data}",
                retry_delay_seconds=delay_seconds,
            )
        if resp.status >= 400:
            logger.error(
                "Chatwoot fatal error response",
                status_code=resp.status,
                tid=tid,
                response=data,
            )
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
        except (ClientError, TimeoutError) as exc:
            logger.error(
                "Chatwoot request transient error",
                method=method,
                url=url,
                tid=tid,
                error=repr(exc),
            )
            raise TransientError(f"Chatwoot request failed: {exc}") from exc
