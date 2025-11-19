[RU](#1-запуск-проекта)

## 1. Running the Project

### Running in Docker

To start the project using Docker, run:

```bash
docker-compose up --build
```

To run in detached (background) mode:

```bash
docker-compose up --build -d
```

> **Note**: When running in Docker, the application is built **without** test dependencies and some development modules.

### For Development

For development, use the [dev_main.py](dev_main.py) script:

```bash
# First, install all dependencies (including dev and extras)
uv sync --all-extras --dev

# Then start the app
python dev_main.py
```

## 2. Environment Variables

> **Important**: All environment variables must be wrapped in quotes, even numeric values.

| Variable                                            | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
|-----------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **BOTS_CONFIG**                                     | This is a list of dictionaries with the following keys:<br>• `connector_id` – unique connector identifier (affects idempotency key). Can be arbitrary at startup, but **do not change** in production after first launch.<br>• `bot_token` – Telegram bot token from `@BotFather`.<br>• `cw_account_id` – Chatwoot account ID (visible in URL: `https://your-chatwoot/app/accounts/{account_id}`).<br>• `cw_inbox_id` – can be found by clicking the link in the browser's Settings after creating an API inbox. The link will look like this: `https://.../app/accounts/{account number}/settings/inboxes/{inbox number}`. |
| **SECRET_TOKEN**                                    | Arbitrary secret token sent by Telegram (or another service) in the header. Used for webhook security. Letters and digits only.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| **CHATWOOT_ACCESS_TOKEN**                           | Personal access token from Chatwoot → Profile Settings → Access Token (bottom of the page).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| **DB_USER / DB_PASS / DB_HOST / DB_PORT / DB_NAME** | PostgreSQL connection parameters. Default port is `5432`. If changed, also update `.test.env` for tests.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| **INCOMING_QUEUE_NAME**<br>**OUTGOING_QUEUE_NAME**  | Database queue table names. Change only if absolutely necessary.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| **WH_DOMAIN**                                       | This app requires a webhook to work. You can use [Cloudflared](https://github.com/cloudflare/cloudflared), [Serveo](https://serveo.net/), [localhost.run](https://localhost.run/). Or Ngrok (where available).                                                                                                                                                                                                                                                                                                                                                                                                              |
| **ENVIRONMENT**                                     | `DEVELOPMENT` or `PRODUCTION`. Overrides certain internal defaults.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| **DEV_BASE_URL**<br>**PROD_BASE_URL**               | Base URL of your Chatwoot instance (used depending on `ENVIRONMENT`).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| **LOG_LEVEL**                                       | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |

## 3. Testing

### PostgreSQL Setup for Tests

Create a dedicated test user with database creation rights:

```sql
CREATE USER test WITH PASSWORD 'test' CREATEDB;
```

Run this as the `postgres` superuser.

### Test Environment

Tests automatically load `.test.env` instead of the regular `.env`. Do not modify `.test.env` unless you know what
you're doing.

### Logging in tests

Tests have logging enabled. If you don't want it, or need a different level, configure it in `pyproject.toml` in the
`[tool.pytest.ini_options]` section. Three parameters are of interest: `log_cli`, `log_cli_format`, `log_cli_level`

## 4. Common Issues & Troubleshooting

1. **Mypy errors**. Delete the `mypy_checks` folder – it contains cached type-checking data that can become corrupted.

2. **PostgreSQL connection problems**. Verify that PostgreSQL is listening on port `5432` (local or Docker container).

3. **Test module naming**. Test files must end with `_test.py` (e.g., `client_test.py`, **not** `test_client.py`) –
   required by pre-commit checks. Individual test functions must start with `test_` (e.g., `test_webhook`).

---

## 1. Запуск проекта

### Запуск в Docker

Для запуска проекта в Docker выполните команду:

```bash
docker-compose up --build
```

Если хотите запустить в фоновом режиме, добавьте флаг `-d`:

```bash
docker-compose up --build -d
```

> **Примечание**: При запуске в Docker приложение собирается без тестовых зависимостей и некоторых модулей.

### Для разработки

Для разработки используйте скрипт [dev_main.py](dev_main.py).
Перед запуском создайте виртуальное окружение:

```bash
uv sync --all-extras --dev
```

После этого можно запустить проект:

```bash
python dev_main.py
```

## 2. Переменные окружения

> **Важно**: Все переменные окружения записываются в кавычках, даже если это цифры.

| Переменная                                          | Описание                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
|-----------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **BOTS_CONFIG**                                     | Это список словарей со следующими ключами:<br>• `connector_id` – название коннектора. Влияет на ключ идемпотентности, поэтому на этапе запуска значение может быть любым. Не рекомендуется изменять после запуска в production во избежание ошибок обработки сообщений.<br>• `bot_token` – токен бота из `@BotFather`.<br>• `cw_account_id` – номер аккаунта в Chatwoot (виден в URL: `https://.../accounts/{номер аккаунта}`).<br>• `cw_inbox_id` – можно узнать по ссылке в браузере в Settings после создания инбокса с типом `API`. Ссылка будет следующего вида: `https://.../app/accounts/{номер аккаунта}/settings/inboxes/{номер инбокса}`. |
| **SECRET_TOKEN**                                    | Произвольный секретный токен, который Telegram (или другой сервис) будет присылать в заголовке. Нужен для защиты вебхука. Допускаются любые буквы и цифры.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| **CHATWOOT_ACCESS_TOKEN**                           | Персональный токен для взаимодействия с API Chatwoot. Можно найти в Profile Settings (не путать с Settings!) в самом низу страницы (Access Token).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| **DB_USER / DB_PASS / DB_HOST / DB_PORT / DB_NAME** | Соответствующие настройки подключения базы данных. Используйте порт `5432` по умолчанию, либо переназначьте на свой. В этом случае, не забудьте исправить порт в `.test.env`, если планируете использовать эту же базу данных и для тестов.                                                                                                                                                                                                                                                                                                                                                                                                         |
| **INCOMING_QUEUE_NAME**<br>**OUTGOING_QUEUE_NAME**  | Названия таблиц-очередей в базе данных. Не меняйте без крайней необходимости!                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| **WH_DOMAIN**                                       | Это приложение требует вебхук для работы. Можно использовать [Cloudflared](https://github.com/cloudflare/cloudflared), [Serveo](https://serveo.net/), [localhost.run](https://localhost.run/). Или Ngrok (доступен не во всех странах).                                                                                                                                                                                                                                                                                                                                                                                                             |
| **ENVIRONMENT**                                     | Допустимые значения: `DEVELOPMENT` или `PRODUCTION`. Переопределяет некоторые переменные проекта.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| **DEV_BASE_URL**<br>**PROD_BASE_URL**               | Базовые URL вашего Chatwoot (используются в зависимости от `ENVIRONMENT`).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| **LOG_LEVEL**                                       | Уровень логирования: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |

## 3. Тестирование

### Подготовка PostgreSQL

Для тестов создайте пользователя `test` с правами на создание баз данных:

```sql
CREATE USER test WITH PASSWORD 'test' CREATEDB;
```

> **Примечание**: Запрос следует выполнять, находясь в аккаунте суперпользователя (`postgres` по умолчанию).

### Переменные окружения для тестов

Для тестов используется файл `.test.env`, который автоматически подгружается вместо `.env`. Не изменяйте его содержимое
без необходимости.

### Логирование в тестах

В тестах включено логирование. Если оно вам не нужно, либо нужен другой уровень - настройте это в `pyproject.toml` в
секции `[tool.pytest.ini_options]`. Вас интересуют три параметра: `log_cli`, `log_cli_format`, `log_cli_level`

## 4. Возможные проблемы

1. **Ошибки mypy**: если столкнулись с нестандартным поведением mypy (ошибки, нехарактерные для проекта), первым делом
   удалите папку `mypy_checks`. Это директория с кешами mypy, и иногда проблемы могут возникать из-за неё.

2. **Проблемы с подключением к PostgreSQL**: убедитесь, что сервер PostgreSQL доступен на порту `5432`. Это может быть как
   локальный сервер, так и контейнер в Docker.

3. **Именование модулей с тестами**: модули с тестами следует называть с постфиксом `test` (например, `client_test`, а
   не `test_client`). Это нужно для того, чтобы проходила проверка на корректность имён файлов в pre-commit. При этом
   сами тесты должны начинаться с префикса `test_` (например, `test_webhook`).



