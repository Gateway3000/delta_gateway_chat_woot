# Delta Chat integration plan

## Цель

Добавить нативный `DeltaChatChannel` в `gateway`, сохранив текущую архитектуру моста:

`Delta Chat -> DeltaChatChannel -> gateway -> Chatwoot`

При этом:

- Chatwoot-логику не переносим из `deltawoot`;
- IMAP/SMTP/MIME/Autocrypt/encryption остаются внутри Delta Chat Core через RPC;
- канал работает как обычный `gateway` plugin;
- миграция проходит постепенно и без двойной отправки.

## План работ

### 1. Зафиксировать контракт

- Использовать `docs/deltachat-integration-analysis.md` как базу.
- Сверить новый канал с `TelegramChannel` и `EmailChannel`.
- Не начинать transport implementation до утверждения contract shape.

### 2. Создать skeleton `DeltaChatChannel`

Предлагаемая структура:

- `channels/deltachat_channel/__init__.py`
- `channels/deltachat_channel/dc_channel.py`
- `channels/deltachat_channel/dc_client.py`
- `channels/deltachat_channel/dc_wiring.py`
- `channels/deltachat_channel/dc_settings.py`
- `channels/deltachat_channel/dc_models.py`

Задача skeleton:

- соответствовать `IChannel`;
- подключаться через entry point;
- быть в стиле существующих каналов;
- не реализовывать лишнюю бизнес-логику.

### 3. Добавить RPC lifecycle для Delta Chat Core

Нужно обернуть `deltachat-rpc-server` / `deltachat-rpc-client` в отдельный client/service слой:

- старт RPC server;
- create RPC client;
- load existing accounts;
- create account if missing;
- configure address/password;
- configure display name/avatar;
- start IO;
- subscribe to events;
- graceful shutdown;
- recovery after restart.

Важно:

- не поднимать отдельный Flask server;
- не реализовывать свой message protocol поверх HTTP;
- не дублировать протокол Delta Chat Core.

### 4. Реализовать inbound flow

Обработать `NewMessage` event и собрать минимум данных:

- `account_id`;
- `connector_id`;
- `message_id`;
- `chat_id`;
- `sender_id`;
- `sender_email/address`.

Дальше сообщение должно:

- стать `Envelope`;
- пройти через обычный `gateway` orchestrator;
- попасть в incoming queue;
- уйти в Chatwoot через общий worker.

### 5. Реализовать outbound flow

`gateway` должен принимать Chatwoot webhook как и для других каналов, а `DeltaChatChannel.send_to_user()` должен:

- резолвить нужный Delta Chat account;
- отправлять text;
- отправлять files;
- сохранять нужный thread/chat context;
- возвращать `ChannelDeliveryResult`.

### 6. Добавить attachments

Переиспользовать только нормализацию attachments на уровне `gateway`/channel adapter.

Не реализовывать:

- MIME parsing;
- decompression;
- encryption/decryption;
- IMAP/SMTP handling.

### 7. Добавить multi-account configuration

Сделать так, чтобы один connector описывал один Delta Chat account.

Нужно хранить mapping:

- `connector_id -> Delta Chat account`
- `Delta Chat account_id -> connector_id`

Требования:

- не хардкодить env vars под один аккаунт;
- хранить отдельный persistent storage для каждого account;
- поддержать несколько аккаунтов в одном deployment.

### 8. Добавить migration flag

Feature flag:

- `ENABLE_NATIVE_DELTACHAT_CHANNEL=true|false`

Поведение:

- `false` - текущая схема через `deltawoot` остаётся рабочей;
- `true` - активируется native channel.

Обязательно:

- исключить двойную публикацию одного и того же сообщения в Chatwoot;
- не позволять `deltawoot` и native channel одновременно доставлять один и тот же event.

### 9. Написать тесты

Минимальный набор:

- channel contract tests;
- routing/config tests;
- idempotency tests;
- lifecycle tests;
- inbound event mapping tests;
- outbound send tests;
- migration flag tests.

### 10. Обновить docker / env / README

Нужно добавить и синхронизировать:

- `Dockerfile`
- `docker-compose.yml`
- `.env.example`
- `README.md`

Также нужно документировать:

- как включать native channel;
- как конфигурировать несколько аккаунтов;
- как проходить миграцию с `deltawoot`.

## Предварительная архитектурная ставка

Для минимального рефакторинга лучше идти так:

- использовать существующий `ChannelRegistry`;
- оставить Chatwoot workers без изменений;
- реализовать Delta Chat как новый channel plugin;
- хранить Delta Chat account state локально в отдельном client/service слое;
- переиспользовать `IdentityStore` и `PGMessageQueue` для mapping/idempotency.

## Что намеренно не делать

- Не переносить Chatwoot API code из `deltawoot`.
- Не строить отдельный HTTP server для Delta Chat.
- Не делать отдельный async worker farm, если текущая модель channel hooks + shared workers достаточна.
- Не переписывать весь `gateway` ради одного канала.

## Риски

- Нужно аккуратно развести legacy `deltawoot` и native channel, чтобы не было дублирования событий.
- Для Delta Chat может понадобиться дополнительная модель persistent mapping, если одного `IdentityStore` окажется недостаточно.
- Multi-account lifecycle и restart recovery нужно проверить особенно тщательно.

