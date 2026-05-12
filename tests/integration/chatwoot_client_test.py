import re

import pytest
from aioresponses import aioresponses

from src.multichannel_gateway.core.exceptions import FatalError, TransientError
from src.multichannel_gateway.infrastructure.chatwoot_client.cw_client import (
    ChatwootClient,
)
from tests.data.chatwoot_test_payloads import (
    BASE_URL,
    ACCOUNT_ID,
    INBOX_ID,
    IDENTIFIER,
    CONTENT,
    CONTACT_IS_FOUND,
    CREATE_CONVERSATION,
    GET_CONVERSATION,
    CREATE_MESSAGE,
    CREATE_CONTACT,
)


class TestDeliverMessage:
    @pytest.mark.asyncio
    async def test_deliver_message_existing_contact_existing_conversation(
        self, client: ChatwootClient
    ) -> None:
        """Contact exists, dialogue exists, just send a message"""

        with aioresponses() as response_mock:
            # 1. The contact exists
            response_mock.get(
                re.compile(
                    re.escape(
                        f"{BASE_URL}/api/v1/accounts/{ACCOUNT_ID}/contacts/search"
                    )
                ),
                payload=CONTACT_IS_FOUND,
            )

            # 2. Retrieve the list of conversations - find the one by inbox_id
            response_mock.get(
                re.compile(
                    re.escape(
                        f"{BASE_URL}/api/v1/accounts/{ACCOUNT_ID}/contacts/34578654/conversations"
                    )
                ),
                payload=GET_CONVERSATION,
            )

            # 3. Send a message
            response_mock.post(
                re.compile(
                    re.escape(
                        f"{BASE_URL}/api/v1/accounts/{ACCOUNT_ID}/conversations/501/messages"
                    )
                ),
                payload=CREATE_MESSAGE,
            )

            await client.deliver_channel_to_chatwoot_message(
                account_id=ACCOUNT_ID,
                end_user_id=IDENTIFIER,
                inbox_id=INBOX_ID,
                content=CONTENT,
                name="John Doe",
                email="john@example.com",
            )

            assert response_mock.requests

            called = [
                f"{method} {url}" for (method, url), _ in response_mock.requests.items()
            ]

            assert len(called) == 3
            assert called[0].startswith("GET") and "contacts/search" in called[0]
            assert (
                called[1].startswith("GET")
                and "conversations" in called[1]
                and "messages" not in called[1]
            )
            assert called[2].startswith("POST") and "messages" in called[2]

    @pytest.mark.asyncio
    async def test_deliver_message_existing_contact_no_conversation(
        self, client: ChatwootClient
    ) -> None:
        """Contact exists, but no dialogue.
        1. Create a new dialogue
        2. Send a message
        """

        with aioresponses() as m:
            # 1. Search - found
            m.get(
                re.compile(
                    re.escape(
                        f"{BASE_URL}/api/v1/accounts/{ACCOUNT_ID}/contacts/search"
                    )
                ),
                payload=CONTACT_IS_FOUND,
            )

            # 2. No conversations are found (or none with the required inbox_id)
            m.get(
                re.compile(
                    re.escape(
                        f"{BASE_URL}/api/v1/accounts/{ACCOUNT_ID}/contacts/34578654/conversations"
                    )
                ),
                payload={"payload": []},
            )

            # 3. Create a new conversation
            m.post(
                f"{BASE_URL}/api/v1/accounts/{ACCOUNT_ID}/conversations",
                payload=CREATE_CONVERSATION,
            )

            # 4. Send a message
            m.post(
                re.compile(
                    re.escape(
                        f"{BASE_URL}/api/v1/accounts/{ACCOUNT_ID}/conversations/501/messages"
                    )
                ),
                payload=CREATE_MESSAGE,
            )

            await client.deliver_channel_to_chatwoot_message(
                account_id=ACCOUNT_ID,
                end_user_id=IDENTIFIER,
                inbox_id=INBOX_ID,
                content=CONTENT,
            )

            assert m.requests

            called = [f"{method} {url}" for (method, url), _ in m.requests.items()]

            assert len(called) == 4

            # 1. Contact search
            assert called[0].startswith("GET") and "contacts/search" in called[0]

            # 2. Fetch conversation list (should be empty)
            assert (
                called[1].startswith("GET")
                and "conversations" in called[1]
                and "messages" not in called[1]
            )

            # 3. Create a new conversation
            assert (
                called[2].startswith("POST")
                and called[2].endswith("/conversations")
                and "messages" not in called[2]
            )

            # 4. Send message to the newly created conversation
            assert called[3].startswith("POST") and "messages" in called[3]

    @pytest.mark.asyncio
    async def test_deliver_message_new_contact(self, client: ChatwootClient) -> None:
        """Contact does not exist.
        1. Create a contact
        2. Create a dialogue
        3. Send a message
        """

        with aioresponses() as m:
            # 1. Search - finds nothing
            m.get(
                re.compile(
                    re.escape(
                        f"{BASE_URL}/api/v1/accounts/{ACCOUNT_ID}/contacts/search"
                    )
                ),
                payload={"payload": []},
            )

            # 2. Create a contact
            m.post(
                f"{BASE_URL}/api/v1/accounts/{ACCOUNT_ID}/contacts",
                payload=CREATE_CONTACT,
            )

            # 3. Create a conversation
            m.post(
                f"{BASE_URL}/api/v1/accounts/{ACCOUNT_ID}/conversations",
                payload=CREATE_CONVERSATION,
            )

            # 4. Send a message
            m.post(
                re.compile(
                    re.escape(
                        f"{BASE_URL}/api/v1/accounts/{ACCOUNT_ID}/conversations/501/messages"
                    )
                ),
                payload=CREATE_MESSAGE,
            )

            await client.deliver_channel_to_chatwoot_message(
                account_id=ACCOUNT_ID,
                end_user_id=IDENTIFIER,
                inbox_id=INBOX_ID,
                content=CONTENT,
                name="Alice",
                email="alice@example.com",
            )

            assert m.requests

            called = [f"{method} {url}" for (method, url), _ in m.requests.items()]

            assert len(called) == 4

            # 1. Contact search - returns nothing
            assert called[0].startswith("GET") and "contacts/search" in called[0]

            # 2. Create a new contact
            assert called[1].startswith("POST") and called[1].endswith("/contacts")

            # 3. Create a new conversation for the newly created contact
            assert (
                called[2].startswith("POST")
                and called[2].endswith("/conversations")
                and "messages" not in called[2]
            )

            # 4. Send message to the newly created conversation
            assert called[3].startswith("POST") and "messages" in called[3]

    @pytest.mark.asyncio
    async def test_deliver_message_unauthorized_error(
        self, client: ChatwootClient
    ) -> None:
        """Check handling of 401"""

        with aioresponses() as m:
            m.get(
                re.compile(
                    re.escape(
                        f"{BASE_URL}/api/v1/accounts/{ACCOUNT_ID}/contacts/search"
                    )
                ),
                status=401,
                payload={"error": "Unauthorized"},
            )

            with pytest.raises(FatalError):
                await client.deliver_channel_to_chatwoot_message(
                    account_id=ACCOUNT_ID,
                    end_user_id=IDENTIFIER,
                    inbox_id=INBOX_ID,
                    content=CONTENT,
                )

    @pytest.mark.asyncio
    async def test_deliver_message_contact_already_exists(
        self, client: ChatwootClient
    ) -> None:
        """When creating a contact, 422 is received"""

        with aioresponses() as m:
            m.get(
                re.compile(
                    re.escape(
                        f"{BASE_URL}/api/v1/accounts/{ACCOUNT_ID}/contacts/search"
                    )
                ),
                payload={"payload": []},
            )

            m.post(
                f"{BASE_URL}/api/v1/accounts/{ACCOUNT_ID}/contacts",
                status=422,
                payload={"error": "Identifier has already been taken"},
            )

            with pytest.raises(FatalError):
                await client.deliver_channel_to_chatwoot_message(
                    account_id=ACCOUNT_ID,
                    end_user_id=IDENTIFIER,
                    inbox_id=INBOX_ID,
                    content=CONTENT,
                )

    @pytest.mark.asyncio
    async def test_deliver_message_server_error(self, client: ChatwootClient) -> None:
        """When creating a contact, 500 is received"""

        with aioresponses() as m:
            m.get(
                re.compile(
                    re.escape(
                        f"{BASE_URL}/api/v1/accounts/{ACCOUNT_ID}/contacts/search"
                    )
                ),
                payload={"payload": []},
            )

            m.post(
                f"{BASE_URL}/api/v1/accounts/{ACCOUNT_ID}/contacts",
                status=500,
                payload={"error": "Server error"},
            )

            with pytest.raises(TransientError):
                await client.deliver_channel_to_chatwoot_message(
                    account_id=ACCOUNT_ID,
                    end_user_id=IDENTIFIER,
                    inbox_id=INBOX_ID,
                    content=CONTENT,
                )

    @pytest.mark.asyncio
    async def test_deliver_message_rate_limit_uses_retry_after(
        self, client: ChatwootClient
    ) -> None:
        """When Chatwoot returns 429, retry delay should come from Retry-After."""

        with aioresponses() as m:
            m.get(
                re.compile(
                    re.escape(
                        f"{BASE_URL}/api/v1/accounts/{ACCOUNT_ID}/contacts/search"
                    )
                ),
                status=429,
                payload={"error": "Too Many Requests"},
                headers={"Retry-After": "120"},
            )

            with pytest.raises(TransientError) as exc_info:
                await client.deliver_channel_to_chatwoot_message(
                    account_id=ACCOUNT_ID,
                    end_user_id=IDENTIFIER,
                    inbox_id=INBOX_ID,
                    content=CONTENT,
                )

        assert exc_info.value.retry_delay_seconds == 120

    @pytest.mark.asyncio
    async def test_deliver_message_rate_limit_invalid_retry_after_falls_back_to_60(
        self, client: ChatwootClient
    ) -> None:
        """When Retry-After is invalid, retry delay should fall back to 60 seconds."""

        with aioresponses() as m:
            m.get(
                re.compile(
                    re.escape(
                        f"{BASE_URL}/api/v1/accounts/{ACCOUNT_ID}/contacts/search"
                    )
                ),
                status=429,
                payload={"error": "Too Many Requests"},
                headers={"Retry-After": "not-a-number"},
            )

            with pytest.raises(TransientError) as exc_info:
                await client.deliver_channel_to_chatwoot_message(
                    account_id=ACCOUNT_ID,
                    end_user_id=IDENTIFIER,
                    inbox_id=INBOX_ID,
                    content=CONTENT,
                )

        assert exc_info.value.retry_delay_seconds == 60

    @pytest.mark.asyncio
    async def test_deliver_message_unexpected_api_error(
        self, client: ChatwootClient
    ) -> None:
        """When creating a contact, 404 is received"""

        with aioresponses() as m:
            m.get(
                re.compile(
                    re.escape(
                        f"{BASE_URL}/api/v1/accounts/{ACCOUNT_ID}/contacts/search"
                    )
                ),
                status=404,
                payload={"error": "Unexpected Chatwoot API error"},
            )

            with pytest.raises(FatalError):
                await client.deliver_channel_to_chatwoot_message(
                    account_id=ACCOUNT_ID,
                    end_user_id=IDENTIFIER,
                    inbox_id=INBOX_ID,
                    content=CONTENT,
                )

    @pytest.mark.asyncio
    async def test_deliver_message_content_type_error(
        self, client: ChatwootClient
    ) -> None:
        """Check for ContentTypeError"""

        with aioresponses() as m:
            m.get(
                re.compile(
                    re.escape(
                        f"{BASE_URL}/api/v1/accounts/{ACCOUNT_ID}/contacts/search"
                    )
                ),
                body="<html><body><h1>500 Internal Server Error</h1></body></html>",
                content_type="text/html",
            )

            with pytest.raises(FatalError):
                await client.deliver_channel_to_chatwoot_message(
                    account_id=ACCOUNT_ID,
                    end_user_id=IDENTIFIER,
                    inbox_id=INBOX_ID,
                    content=CONTENT,
                )
