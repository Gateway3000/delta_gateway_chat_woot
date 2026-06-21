# Delta Chat integration analysis

## Цель

Этот документ фиксирует текущую архитектуру `gateway` и показывает, как в неё должен встраиваться нативный `DeltaChatChannel`, не перенося Chatwoot-логику и не реализуя заново протоколы Delta Chat Core.

Проанализированы:

- `gateway`
- `deltawoot`
- `deltabot-cli-py`

## Ключевой вывод

`gateway` уже является общим мостом между каналами и Chatwoot:

- канал нормализует payload в `Envelope`;
- канал публикует сообщение в PGMQ;
- общий worker доставляет сообщение в Chatwoot;
- webhook из Chatwoot проходит обратный путь через общий worker в канал;
- идемпотентность и identity mapping уже лежат в `gateway`, а не в канале.

Это значит, что для Delta Chat нужно реализовать только transport layer и channel adapter, а не переносить бизнес-логику Chatwoot.

## 1. Интерфейс канала в `gateway`

### Где находится контракт

Контракт канала определён в `src/multichannel_gateway/core/interfaces/channel.py`.

### Что обязан реализовать канал

`IChannel` требует следующие методы:

- `get_route_by_connector_id(connector_id: str) -> dict[str, str]`
- `send_to_user(message: dict[str, Any], limiter: Any = None) -> ChannelDeliveryResult`
- `build_channel_message(raw_data: dict[str, Any]) -> tuple[str, Envelope]`
- `publish_channel_message(idempotency_key: str, envelope: Envelope, raw_data: dict[str, Any]) -> None`
- `publish_chatwoot_message(raw_data: dict[str, Any], cw_account_id: str) -> None`

Также есть lifecycle hooks:

- `on_prefork()`
- `on_startup()`
- `on_shutdown()`

### Что видно по Telegram и Email

`TelegramChannel` и `EmailChannel` следуют одному стилю:

- channel class держит ссылки на routing, transport, processor и lifecycle helper;
- `build_channel_message()` и `publish_*()` делегируются processor-слою;
- `send_to_user()` делегируется transport-слою;
- `get_route_by_connector_id()` делегируется routing-слою;
- lifecycle hooks используются для подготовки соединений и background watchers.

Файлы для ориентира:

- `channels/telegram_channel/tg_channel.py`
- `channels/email_channel/email_channel.py`

## 2. Как channel plugin регистрируется через entry points

### Регистрация

В `pyproject.toml` каналы регистрируются в группе:

`multichannel_gateway.channels`

Примеры из текущего `gateway`:

- `telegram = "channels.telegram_channel.tg_wiring:telegram_channel"`
- `email = "channels.email_channel.email_wiring:email_channel"`
- `delta_chat = "channels.delta_chat_channel.dc_wiring:delta_chat_channel"`

### Как происходит discovery

`ChannelRegistry.discover_channels("multichannel_gateway.channels")`:

- читает entry points через `importlib.metadata.entry_points()`;
- загружает каждый plugin instance;
- складывает его в реестр по `channel.channel`;
- умеет фильтровать по `CHANNELS`.

### Когда discovery запускается

Сейчас discovery вызывается до старта приложения:

- в `tests/conftest.py` через session fixture;
- в `app` lifecycle через `registry.on_startup()` после discovery;
- в bootstrap ожидается, что discovery уже выполнен до worker startup.

## 3. Путь входящего сообщения: channel -> orchestrator -> incoming queue -> Chatwoot

### 3.1. Вход в `gateway`

HTTP endpoints:

- `POST /ingest/incoming/{channel}/{connector_id}/webhook`
- `POST /messages/inbound`

Оба endpoint:

- читают JSON;
- проставляют `channel` и `connector_id`;
- вызывают `handle_channel_payload()`.

### 3.2. Orchestrator

`handle_channel_payload()` вызывает:

- `channel_to_chatwoot_orchestrator.process(channel, payload)`

`ChannelToChatwootOrchestrator.process()`:

- берёт канал из `ChannelRegistry`;
- вызывает `channel.build_channel_message(raw_data)`;
- для не-`delta_chat` каналов может переписать `sender.external_id` и сохранить `sender.raw_external_id`;
- при анонимизации может заменить `sender.name`;
- вызывает `channel.publish_channel_message(...)`.

### 3.3. Channel -> queue

`publish_channel_message()` в channel implementation:

- проверяет idempotency key в `pgmq.processed_keys`;
- отправляет `Envelope` в incoming queue;
- помечает key как processed.

По текущему соглашению incoming queue называется:

- `to_cw`

### 3.4. Queue -> Chatwoot

`ChannelToChatwootWorker` читает сообщения из incoming queue и вызывает:

- `ChatwootClient.deliver_channel_to_chatwoot_message(...)`

В worker используются поля `Envelope`:

- `channel`
- `connector_id`
- `cw_account_id`
- `cw_inbox_id`
- `sender.external_id`
- `sender.name`
- `payload.text`
- `payload.attachments`

## 4. Путь исходящего сообщения: Chatwoot webhook -> outgoing queue -> channel

### 4.1. Вход в `gateway`

HTTP endpoints:

- `POST /ingest/outgoing/{channel}/{cw_account_id}/webhook`
- `POST /messages/outbound`

Оба endpoint:

- читают JSON;
- вызывают `handle_chatwoot_payload()`.

### 4.2. Webhook handling

`handle_chatwoot_payload()`:

- проверяет `message_type == "outgoing"`;
- для не-`delta_chat` каналов снимает channel prefix из `conversation.meta.sender.identifier`;
- находит channel через `ChannelRegistry`;
- вызывает `channel.publish_chatwoot_message(payload, cw_account_id)`.

### 4.3. Channel -> outgoing queue

`publish_chatwoot_message()`:

- строит `Envelope`;
- проверяет idempotency key;
- отправляет сообщение в outgoing queue;
- помечает key как processed.

По текущему соглашению outgoing queue называется:

- `from_cw`

### 4.4. Queue -> channel

`ChatwootToChannelWorker` читает outgoing queue и вызывает:

- `channel.send_to_user(payload)`

`send_to_user()` возвращает `ChannelDeliveryResult`.

## 5. Модели Gateway

### Входящее сообщение

Основная модель:

- `src/multichannel_gateway/core/core_models.py::Envelope`

Используется для обоих направлений.

Ключевые поля:

- `idem_key`
- `channel`
- `from_`
- `to`
- `connector_id`
- `cw_inbox_id`
- `cw_account_id`
- `message_id`
- `sender`
- `payload`
- `ts`

### Исходящее сообщение

Тоже `Envelope`, но со значениями:

- `from_="chatwoot"`
- `to=<channel>`

### Attachments

Модельный слой находится в:

- `src/multichannel_gateway/core/attachment_models.py`

Типы:

- `UploadedAttachment`
- `Base64Attachment`

В текущем gateway attachments часто проходят как список dict-подобных объектов внутри `Envelope.payload["attachments"]`, а затем преобразуются channel-specific helper’ами.

### External user ID

Сейчас это поле живёт в:

- `SenderInfo.external_id`

Дополнительно есть:

- `SenderInfo.raw_external_id`

`raw_external_id` полезен для сохранения канал-нэйтивного ID до нормализации.

### External chat ID

В текущем базовом `Envelope` нет отдельного обязательного поля `external_chat_id`.

Практика сейчас такая:

- channel-specific processors кладут chat/thread/conversation id в `payload` или в extra-поля idempotency key;
- пример из email: thread-related данные живут через IMAP UID/UIDVALIDITY;
- пример из Delta Chat WIP: conversation id используется как extra для idempotency.

Итого: для native Delta Chat, скорее всего, понадобится отдельное хранение thread/chat mapping на уровне channel plugin, а не в базовом `Envelope`.

### Connector ID

Это first-class поле:

- `Envelope.connector_id`

Именно его использует routing и idempotency contract.

## 6. Где и как строится idempotency key

### Базовый контракт

Функция:

- `IEnvelopeFactory.build_idempotency_key(...)`

Формат:

`{direction}:{connector_id}:{extra_hash}:{external_id_hash}:{message_id_hash}`

### Алгоритм

- обязательны `external_id` и `message_id`;
- все переменные части хешируются через `sha1`;
- длина каждого хеша сокращена до 12 символов;
- `extra` сортируется по ключам перед хешированием;
- при пустом `extra` используется заглушка `000000000000`.

### Где проверяется идемпотентность

`PGMessageQueue` хранит processed keys в таблице:

- `pgmq.processed_keys`

Методы:

- `is_already_processed(key)`
- `mark_as_processed(key)`

### Как это используется в channel code

Перед публикацией в очередь channel проверяет key и только потом кладёт сообщение в queue.

## 7. Где хранится mapping между external chat/user и Chatwoot contact/conversation

### Что уже есть в `gateway`

Есть таблица:

- `identity_mappings`

Через `IdentityStore` она хранит:

- `channel`
- `external_id`
- `actor_id`

То есть текущий mapping в `gateway` — это не Chatwoot contact/conversation mapping, а внутренний mapping между внешним ID и внутренним actor ID.

### Чего сейчас нет

В текущем committed baseline нет отдельной persistent таблицы, которая бы хранила:

- external chat id -> Chatwoot conversation id
- external user id -> Chatwoot contact id

Эта связь пока либо:

- подразумевается Chatwoot API;
- либо поддерживается косвенно через `conversation.meta.sender.identifier`;
- либо хранится в channel-specific transport logic.

### Что это значит для Delta Chat

Для native Delta Chat, скорее всего, придётся:

- сохранить mapping Delta Chat account <-> connector_id;
- сохранить mapping Delta Chat peer/user/thread identifiers там, где это нужно для повторной маршрутизации;
- не дублировать Chatwoot contact/conversation state, если его уже даёт Chatwoot.

## 8. Что можно переиспользовать из `gateway`

Можно переиспользовать напрямую:

- `IChannel` contract;
- `Envelope`, `SenderInfo`, `ChannelDeliveryResult`;
- `ChannelRegistry` discovery mechanism;
- `ChannelToChatwootOrchestrator`;
- `ChannelToChatwootWorker` и `ChatwootToChannelWorker`;
- `PGMessageQueue` idempotency storage;
- `IdentityStore` как базу под actor mapping;
- `ChatwootClient`;
- existing FastAPI webhook routing.

## 9. Что было перенесено/извлечено из `deltawoot`

Из `deltawoot` имеет смысл переносить только Delta Chat transport logic:

- настройка аккаунта;
- запуск RPC/core;
- подписка на события;
- обработка `NewMessage`;
- отправка текста;
- отправка файлов;
- secure join;
- help-команда;
- поведение в группах;
- graceful shutdown / restart recovery.

### Что не переносить

Не переносим из `deltawoot`:

- отдельный Flask server;
- Chatwoot API code;
- создание Chatwoot inbox/contact/conversation;
- own message delivery to Chatwoot;
- download-from-Chatwoot logic;
- IMAP/SMTP/MIME stack;
- encryption/decryption stack;
- any ad-hoc contact mapping inside Delta Chat config.

## 10. Что показывает `deltabot-cli-py`

`deltabot-cli-py` полезен как reference по lifecycle Delta Chat bot, но не как прямой runtime для `gateway`.

Полезные идеи:

- start/init/on_start hooks;
- event-driven handling via `events.NewMessage` и `events.RawEvent`;
- account bootstrap;
- send/receive patterns;
- group/admin/help-style commands.

Но для `gateway` нужен именно channel plugin, который живёт в архитектуре `gateway`, а не standalone bot CLI.

## 11. Риски и открытые точки

- Сейчас в рабочем дереве уже есть черновой `delta_chat_channel`; его нужно сверить с этим контрактом и не сломать существующие каналы.
- В базовой модели нет first-class `external_chat_id`; для Delta Chat это почти наверняка понадобится как channel-specific detail.
- Нужен явный migration flag, чтобы не допустить двойную отправку в Chatwoot во время coexistence с `deltawoot`.
- Модель persistent storage для multi-account Delta Chat пока отсутствует и будет новым слоем конфигурации.

