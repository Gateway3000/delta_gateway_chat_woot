# Настройка Email Channel

## Назначение

Документ описывает настройку Email Channel для двусторонней работы: получение входящих писем через IMAP, отправка
ответов через SMTP, и интеграция с Chatwoot.

## Что делает канал

### Email → Chatwoot

- Периодически опрашивает IMAP mailbox
- Ищет непрочитанные письма (UNSEEN)
- Парсит MIME: заголовки, тело, вложения
- Публикует сообщение в PGMQ (`incoming_queue_name`)
- Помечает письмо как прочитанное (`\Seen` flag)
- Общий `ChannelToChatwootWorker` забирает сообщение из очереди и отправляет в Chatwoot

### Chatwoot → Email

- Общий endpoint `/ingest/outgoing/email/{cw_account_id}/webhook` принимает webhook от Chatwoot
- Сообщение публикуется в PGMQ (`outgoing_queue_name`)
- `ChatwootToChannelWorker` читает сообщение из очереди
- `EmailTransport` отправляет письмо через Gmail SMTP с STARTTLS
- Поддерживает threading headers (`In-Reply-To`, `References`)
- Поддерживает вложения из Chatwoot (скачивание по `data_url`, лимит задаётся параметром `channel_upload_max_mb` в
  настройках плагина: `email_channel/plugin_settings.py`)
- Возвращает `ChannelDeliveryResult` со статусом доставки

## Предварительные требования

### 1. Gmail аккаунт

- Включите 2-факторную аутентификацию в Google аккаунте
- Создайте App Password:
    1. Перейдите в [Google Account → Security](https://myaccount.google.com/security)
    2. Включите 2-Step Verification (если ещё не включена)
    3. Перейдите в [App Passwords](https://myaccount.google.com/apppasswords)
    4. Создайте новый app password (например, "Channel Gateway")
    5. Сохраните сгенерированный 16-значный пароль

### 2. Chatwoot Inbox

- Создайте API Inbox в Chatwoot или используйте существующий
- Запишите `cw_account_id` и `cw_inbox_id` (доступны в URL и настройках inbox)
- Настройте outgoing webhook в Chatwoot, указав URL Gateway

### 3. Базовая инфраструктура

- Зависимости проекта установлены (`uv sync`)
- Запущен Postgres с расширением PGMQ
- Запущен Gateway

## Конфигурация

### Переменная окружения `MAILBOXES_CONFIG`

Добавьте в `.env` JSON-массив mailbox конфигураций:

```env
MAILBOXES_CONFIG='[{
  "connector_id": "email-support",
  "cw_account_id": "1",
  "cw_inbox_id": "10",
  "imap_username": "support@gmail.com",
  "imap_password": "abcdefghijklmnop",
  "smtp": {
    "smtp_username": "support@gmail.com",
    "smtp_password": "abcdefghijklmnop",
    "smtp_from": "support@gmail.com"
  }
}]'
```

### Переменная окружения `POLL_INTERVAL_SECONDS`

Интервал опроса IMAP почтового ящика в секундах.

```env
POLL_INTERVAL_SECONDS=5.0
```

| Поле | Тип | По умолчанию | Описание |
|------|-----|-------------|----------|
| `POLL_INTERVAL_SECONDS` | float | `5.0` | Интервал между последовательными проверками IMAP (в секундах) |

### Параметры конфигурации

| Поле                 | Тип       | Обязательное | Описание                                            |
|----------------------|-----------|--------------|-----------------------------------------------------|
| `connector_id`       | str       | Да           | Уникальный идентификатор коннектора                 |
| `cw_account_id`      | str       | Да           | Account ID в Chatwoot                               |
| `cw_inbox_id`        | str       | Да           | Inbox ID в Chatwoot                                 |
| `imap_username`      | str       | Да           | Email адрес для IMAP                                |
| `imap_password`      | str       | Да           | App Password для IMAP                               |
| `smtp.smtp_username` | str       | Да           | Email для SMTP отправки                             |
| `smtp.smtp_password` | str       | Да           | App Password для SMTP                               |
| `smtp.smtp_from`     | str       | Да           | From адрес для исходящих писем                      |
| `smtp.smtp_host`     | str       | Нет          | SMTP хост, по умолчанию `smtp.gmail.com`            |
| `smtp.smtp_port`     | int       | Нет          | SMTP порт, по умолчанию `587`                       |
| `smtp.smtp_use_tls`  | bool      | Нет          | Использовать STARTTLS, по умолчанию `true`          |
| `imap_host`          | str       | Нет          | IMAP хост, по умолчанию `imap.gmail.com`            |
| `imap_port`          | int       | Нет          | IMAP порт, по умолчанию `993`                       |
| `imap_mailbox`       | str       | Нет          | IMAP mailbox, по умолчанию `INBOX`                  |
| `imap_use_ssl`       | bool      | Нет          | Использовать SSL, по умолчанию `true`               |
| `processed_folder`   | str\|None | Нет          | Папка для обработанных писем (пока не используется) |

### Несколько mailbox

Для подключения нескольких email ящиков добавьте элементы в массив:

```env
MAILBOXES_CONFIG='[
  {"connector_id": "email-support", "cw_account_id": "1", "cw_inbox_id": "10", "imap_username": "support@gmail.com", "imap_password": "password1", "smtp": {"smtp_username": "support@gmail.com", "smtp_password": "password1", "smtp_from": "support@gmail.com"}},
  {"connector_id": "email-sales", "cw_account_id": "1", "cw_inbox_id": "20", "imap_username": "sales@gmail.com", "imap_password": "password2", "smtp": {"smtp_username": "sales@gmail.com", "smtp_password": "password2", "smtp_from": "sales@gmail.com"}}
]'
```

## Запуск

### 1. Проверьте entry point

```bash
uv run python -c "from importlib.metadata import entry_points; print([f'{e.name}={e.value}' for e in entry_points().select(group='multichannel_gateway.channels')])"
```

Ожидается вывод:

```
['telegram=telegram.tg_wiring:telegram_channel', 'email=email_channel.email_wiring:email_channel']
```

### 2. Запустите Gateway

```bash
uv run python -m src.multichannel_gateway.main
```

### 3. Проверьте логи

При успешном подключении к IMAP, watcher начнёт polling.

При ошибке подключения вы увидите:

```
IMAP connection attempt failed  connector_id=email-support attempt=1 max_attempts=5 error=...
```

После 5 неудачных попыток (с интервалом 60 секунд):

```
IMAP connection failed after all retries  connector_id=email-support max_attempts=5
```

## Проверка работы

### Email → Chatwoot

1. Отправьте email на адрес, указанный в `imap_username`.
2. Через некоторое время watcher заберёт письмо из IMAP и отправит в очередь.
3. Новое сообщение должно появиться в соответствующем Chatwoot Inbox (`cw_inbox_id`).

### Chatwoot → Email

1. Откройте conversation в Chatwoot Inbox.
2. Отправьте ответ оператором.
3. Chatwoot отправит webhook на Gateway.
4. Gateway опубликует сообщение в очередь.
5. `ChatwootToChannelWorker` заберёт сообщение и вызовет `EmailChannel.send_to_user()`.
6. Письмо будет отправлено через Gmail SMTP.

## Threading

- При получении входящего письма сохраняется `Message-ID`.
- При ответе из Chatwoot выставляются `In-Reply-To` и `References` для сохранения цепочки писем.
- Если исходный `Message-ID` недоступен, письмо отправляется как новая цепочка.

## Troubleshooting

### Connection refused

- Проверьте, что IMAP включен в настройках Gmail
- Убедитесь, что App Password создан корректно (16 символов)
- Попробуйте подключиться вручную: `openssl s_client -connect imap.gmail.com:993`

### Authentication failed

- App Password должен быть введён без пробелов: `abcdefghijklmnop` вместо `abcd efgh ijkl mnop`
- Проверьте, что 2FA включена в Google аккаунте

### Письма не попадают в Chatwoot

- Проверьте, что Postgres запущен и PGMQ доступен
- Убедитесь, что `cw_account_id` и `cw_inbox_id` корректны
- Проверьте, что `ChannelToChatwootWorker` запущен

### Ответы не доходят до пользователя

- Проверьте, что `ChatwootToChannelWorker` запущен
- Проверьте логи на наличие SMTP ошибок (аутентификация, rate limit, недоступность)
- Убедитесь, что `smtp.smtp_from` корректный и совпадает с `imap_username`

## Ограничения текущей версии

- Поддерживается только Gmail IMAP/SMTP
- Нет IMAP IDLE (только polling)
- Лимит вложений задаётся параметром `channel_upload_max_mb` (настройки плагина: `email_channel/plugin_settings.py`)
