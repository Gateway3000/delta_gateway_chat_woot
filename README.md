[RU](#1-запуск-проекта)

## 1. Running the Project

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

### Running in Docker

Build the project:

```bash
docker buildx bake -f docker-bake.hcl
```

To start the project using Docker, run:

```bash
# Do this only once
echo COMPOSE_FILE=docker-compose.yml:docker-compose.local.yml >> .env
```

```bash
docker compose up
```

> **Note**: if you are on Windows, use the following commands:
> ```bash
> wsl bash -lc "echo 'COMPOSE_FILE=docker-compose.yml:docker-compose.local.yml' >> .env"
> ```
>
> ```bash
> wsl bash -lc "docker compose up"
> ```

To run in detached (background) mode:

```bash
docker compose up -d
```

> **Note**: When running in Docker, the application is built **without** test dependencies and some development modules.

### For Development

To run the project, use [main.py](main.py). For development, the variable `ENVIRONMENT` should be set to "LOCAL".
First, install all dependencies (including dev and extras):

```bash
uv sync --all-extras --dev
```

Then start the app:

```bash
python main.py
```

## 2. Environment Variables

> **Important**: All environment variables in `BOTS_CONFIG` must be wrapped in quotes, even numeric values.

| Variable                                            | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
|-----------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **POSTGRES_VERSION**                                | Postgres version in use.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| **PGMQ_VERSION**                                    | PGMQ version in use.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| **BOTS_CONFIG**                                     | This is a list of dictionaries with the following keys:<br>• `connector_id` – unique connector identifier (affects idempotency key). Can be arbitrary at startup, but **do not change** in production after first launch.<br>• `bot_token` – Telegram bot token from `@BotFather`.<br>• `cw_account_id` – Chatwoot account ID (visible in URL: `https://your-chatwoot/app/accounts/{account_id}`).<br>• `cw_inbox_id` – can be found by clicking the link in the browser's Settings after creating an API inbox. The link will look like this: `https://.../app/accounts/{account number}/settings/inboxes/{inbox number}`. |
| **SECRET_TOKEN**                                    | Arbitrary secret token sent by Telegram (or another service) in the header. Used for webhook security. Letters and digits only.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| **CHATWOOT_ACCESS_TOKEN**                           | Personal access token from Chatwoot → Profile Settings → Access Token (bottom of the page).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| **DB_USER / DB_PASS / DB_HOST / DB_PORT / DB_NAME** | PostgreSQL connection parameters. Default port is `5432`. If changed, also update `.env.test` for tests.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| **TEST_CONTAINER**                                  | Controls PostgreSQL Testcontainers usage in tests. If set to `false` or `0`, tests use the DB from `.env.test` without starting a container. Any other value (or unset) starts a temporary container and overrides `DB_HOST`/`DB_PORT` for the test session. This variable is useful if you do not have a local Postgres instance (or a compatible version) and prefer to start a clean disposable container for each test run. If you already have Postgres on `5432` and do not need an extra container, set this variable to `False`.                                                                                                      |
| **INCOMING_QUEUE_NAME**<br>**OUTGOING_QUEUE_NAME**  | Database queue table names. Change only if absolutely necessary.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| **WH_DOMAIN**                                       | This app requires a webhook to work. You can use [Cloudflared](https://github.com/cloudflare/cloudflared) (see below), [Serveo](https://serveo.net/), [localhost.run](https://localhost.run/). Or Ngrok (where available).                                                                                                                                                                                                                                                                                                                                                                                                  |
| **GROUP**                                           | Group for plugin auto-discovery.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| **ENVIRONMENT**                                     | `LOCAL`, `DEV`, `STAGE` or `PROD`. Overrides certain internal defaults.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| **CHATWOOT_BASE_URL**                               | Base URL of your Chatwoot instance.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| **LOG_LEVEL**                                       | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| **ANONYMIZE_USERS**                                 | Generates a random username made up of numbers, an adjective, and a noun                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |

## 3. Testing

### PostgreSQL Setup for Tests

Create a dedicated test user with database creation rights:

```sql
CREATE USER test WITH PASSWORD 'test' CREATEDB;
```

Run this as the `postgres` superuser.

### Test Environment

Tests automatically load `.env.test` instead of the regular `.env`. Do not modify it unless you know what
you're doing.

### Logging in tests

Tests have logging enabled. If you don't want it, or need a different level, configure it in `pyproject.toml` in the
`[tool.pytest.ini_options]` section. Three parameters are of interest: `log_cli`, `log_cli_format`, `log_cli_level`

## 4. Pre-commit

In the project, [pre-commit](https://pre-commit.com/) is used. To apply it, it must be installed in Git:

```bash
pre-commit install
```

Thus, it will run before every commit. To run it manually, use the command:

```bash
pre-commit run --all-files
```

## 5. Chatwoot Webhook

The webhook specified in Chatwoot must follow the format:

```https://your-domain-name.com/ingest/outgoing/{channel}/{cw_account_id}/webhook```

where:

- `{channel}` is the name of the channel to which you send a message from Chatwoot (e.g., `telegram`). The channel name
  must exactly match the `channel` attribute of the `IChannel` instance.
- `{cw_account_id}` is the identifier of your Chatwoot Account, which corresponds to the environment variable with the
  same name.

### 5.1 Using Cloudflare Tunnels to Create a Webhook for Local Development

Requirements:

1. Cloudflare account (free)
2. Domain name on Cloudflare DNS
3. Server (optional for Europe, mandatory for Russia. Cloudflare is blocked in Russia)

First, create a tunnel: `Access` -> `Launch Zero Trust` -> `Networks` -> `Connectors` -> `Create a tunnel`. Choose
Cloudflared, give it a name, and click Save. You will then be prompted to select an operating system or environment.
Here, choose Docker. Below, you will see a command like this:

```bash
docker run cloudflare/cloudflared:latest tunnel --no-autoupdate run --token xxxxxxxxxxxxxxxxxxxxxxxxxxx
```

This needs to be slightly modified to the following:

```bash
docker run -d \
  --name cloudflared-webhook \
  --restart unless-stopped \
  --network host \
  cloudflare/cloudflared:latest \
  tunnel --no-autoupdate run --token xxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Continue with the tunnel setup. After selecting Docker, click `Next` in the bottom right corner.
This will open the **Route Traffic** panel, where you need to link the tunnel to your domain name.
In the subdomain field, enter something like `mytunnel`, and select your domain.
Leave the Path field empty (you can also specify a full or partial path to the webhook here to filter out
unnecessary requests from the internet).

> **Important!** In the Service -> Type field, select **HTTP**, not HTTPS! In the URL field, enter
> `127.0.0.1:<any port above 2000>`. You can use the same `8000` that your application is running on.

Next, log into the server, install Docker (if it’s not already installed), and run the command in the terminal. The
image will be downloaded, and the container will start. You can check the logs with:

```bash
docker logs <container name> --tail 100
```

Ensure there are no connection errors in the logs. Also, check the tunnel status in `Zero Trust` -> `Networks` ->
`Connectors`: the tunnel should be marked as Healthy.

Open the local console and run the following command:

```bash
ssh -N -i <path to SSH key> -R 8000:0.0.0.0:8000 <login>@<server ip>
```

Make sure to replace the port with the one you specified in Cloudflare!
Now, as long as the SSH tunnel is active, all requests will be forwarded to your local machine.

> **Note for countries where Cloudflare is not blocked**: You can complete the first domain setup step and, instead of
> using a server, run the default command on your local machine:
> ```bash
> docker run cloudflare/cloudflared:latest tunnel --no-autoupdate run --token xxxxxxxxxxxxxxxxxxxxxxxxxxx
> ```

## 6. Common Issues & Troubleshooting

1. **Mypy errors**. Delete the `mypy_checks` folder – it contains cached type-checking data that can become corrupted.

2. **PostgreSQL connection problems**. Verify that PostgreSQL is listening on port `5432` (local or Docker container).

3. **Test module naming**. Test files must end with `_test.py` (e.g., `client_test.py`, **not** `test_client.py`) –
   required by pre-commit checks. Individual test functions must start with `test_` (e.g., `test_webhook`).

4. If `buildx bake -f docker-bake.hcl` throws an error, check your Docker version. It must be 29.1.5 or later.

---
[EN](#1-running-the-project)

## 1. Запуск проекта

Скопируйте `.env.example` в `.env`:

```bash
cp .env.example .env
```

### Запуск в Docker

Соберите проект:

```bash
docker buildx bake -f docker-bake.hcl
```

Для запуска проекта в Докере используйте команды:

```bash
# Сделайте это только один раз
echo COMPOSE_FILE=docker-compose.yml:docker-compose.local.yml >> .env
```

```bash
docker compose up
```

> **Примечание**: если у вас Windows, используйте команды:
> ```bash
> wsl bash -lc "echo 'COMPOSE_FILE=docker-compose.yml:docker-compose.local.yml' >> .env"
> ```
>
> ```bash
> wsl bash -lc "docker compose up"
> ```

Если хотите запустить в фоновом режиме, добавьте флаг `-d`:

```bash
docker compose up -d
```

> **Примечание**: При запуске в Docker приложение собирается без тестовых зависимостей и некоторых модулей.

### Для разработки

Для запуска проекта, используйте [main.py](main.py). Для разработки, значение переменной `ENVIRONMENT` должно быть
равно "LOCAL".
Перед запуском создайте виртуальное окружение:

```bash
uv sync --all-extras --dev
```

После этого можно запустить проект:

```bash
python main.py
```

## 2. Переменные окружения

> **Важно**: Все переменные окружения в `BOTS_CONFIG` записываются в кавычках, даже если это цифры.

| Переменная                                          | Описание                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
|-----------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **POSTGRES_VERSION**                                | Используемая версия Postgres.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| **PGMQ_VERSION**                                    | Используемая версия PGMQ.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| **BOTS_CONFIG**                                     | Это список словарей со следующими ключами:<br>• `connector_id` – название коннектора. Влияет на ключ идемпотентности, поэтому на этапе запуска значение может быть любым. Не рекомендуется изменять после запуска в production во избежание ошибок обработки сообщений.<br>• `bot_token` – токен бота из `@BotFather`.<br>• `cw_account_id` – номер аккаунта в Chatwoot (виден в URL: `https://.../accounts/{номер аккаунта}`).<br>• `cw_inbox_id` – можно узнать по ссылке в браузере в Settings после создания инбокса с типом `API`. Ссылка будет следующего вида: `https://.../app/accounts/{номер аккаунта}/settings/inboxes/{номер инбокса}`. |
| **SECRET_TOKEN**                                    | Произвольный секретный токен, который Telegram (или другой сервис) будет присылать в заголовке. Нужен для защиты вебхука. Допускаются любые буквы и цифры.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| **CHATWOOT_ACCESS_TOKEN**                           | Персональный токен для взаимодействия с API Chatwoot. Можно найти в Profile Settings (не путать с Settings!) в самом низу страницы (Access Token).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| **DB_USER / DB_PASS / DB_HOST / DB_PORT / DB_NAME** | Соответствующие настройки подключения базы данных. Используйте порт `5432` по умолчанию, либо переназначьте на свой. В этом случае, не забудьте исправить порт в `.env.test`, если планируете использовать эту же базу данных и для тестов.                                                                                                                                                                                                                                                                                                                                                                                                         |
| **TEST_CONTAINER**                                  | Управляет использованием PostgreSQL Testcontainers в тестах. Если установлено `false` или `0`, тесты используют БД из `.env.test` и не поднимают контейнер. В остальных случаях (или если переменная не задана) стартует временный контейнер, а `DB_HOST`/`DB_PORT` переопределяются на время тестовой сессии. Эта переменная полезна в случае, если у вас нет Postgres (или подходящей версии) и вам удобнее каждый раз поднимать чистый контейнер, который удаляется после тестов. Если же у вас уже есть Postgres на `5432` и вам не нужен дополнительный контейнер, задайте этой переменной значение `False`                                      |
| **INCOMING_QUEUE_NAME**<br>**OUTGOING_QUEUE_NAME**  | Названия таблиц-очередей в базе данных. Не меняйте без крайней необходимости!                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| **WH_DOMAIN**                                       | Это приложение требует вебхук для работы. Можно использовать [Cloudflared](https://github.com/cloudflare/cloudflared) (подробнее смотри ниже), [Serveo](https://serveo.net/), [localhost.run](https://localhost.run/). Или Ngrok (доступен не во всех странах).                                                                                                                                                                                                                                                                                                                                                                                     |
| **GROUP**                                           | Группа для автоопределения плагинов.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| **ENVIRONMENT**                                     | Допустимые значения: `LOCAL`, `DEV`, `STAGE` или `PROD`. Переопределяет некоторые переменные проекта.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| **CHATWOOT_BASE_URL**                               | Базовая URL вашего Chatwoot.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| **LOG_LEVEL**                                       | Уровень логирования: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| **ANONYMIZE_USERS**                                 | Генерирует произвольное имя пользователя, состоящее из цифр, прилагательного и существительного                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |

## 3. Тестирование

### Подготовка PostgreSQL

Для тестов создайте пользователя `test` с правами на создание баз данных:

```sql
CREATE USER test WITH PASSWORD 'test' CREATEDB;
```

> **Примечание**: Запрос следует выполнять, находясь в аккаунте суперпользователя (`postgres` по умолчанию).

### Переменные окружения для тестов

Для тестов используется файл `.env.test`, который автоматически подгружается вместо `.env`. Не изменяйте его содержимое
без необходимости.

### Логирование в тестах

В тестах включено логирование. Если оно вам не нужно, либо нужен другой уровень - настройте это в `pyproject.toml` в
секции `[tool.pytest.ini_options]`. Вас интересуют три параметра: `log_cli`, `log_cli_format`, `log_cli_level`

## 4. Pre-commit

В проекте используется [pre-commit](https://pre-commit.com/). Для его применения, его необходимо проинсталлировать в
Git:

```bash
pre-commit install
```

Таким образом, он будет запускаться **перед каждым коммитом**. Для мануального запуска используйте команду:

```bash
pre-commit run --all-files
```

## 5. Webhook в Chatwoot

Вебхук, указанный в Chatwoot, должен соответствовать следующему формату:

```https://your-domain-name.com/ingest/outgoing/{channel}/{cw_account_id}/webhook```,

где:

- `{channel}` - это имя
  канала, в который вы отправляете сообщение из Chatwoot (например, `telegram`). Имя канала должно строго совпадать с
  атрибутом класса `channel` в экземпляре `IChannel`.
- `{cw_account_id}` - это идентификатор вашего Chatwoot Account,
  который соответствует одноименной переменной окружения.

### 5.1 Использование Cloudflare tunnels для создания вебхука для локальной разработки

Понадобится:

1. Аккаунт Cloudflare (бесплатный)
2. Доменное имя на DNS Cloudflare
3. Сервер (для Европы опционально, для РФ - обязательно. В РФ Cloudflare заблокирован)

Создаём туннель: `Access` -> `Launch Zero Trust` -> `Networks` -> `Connectors` ->
`Create a tunnel`. Выбираем Cloudflared, даем ему имя и нажимаем Save. Будет предложен выбор ОС или среды. Здесь
выбираем Docker. Чуть ниже появится комманда вида:

```bash
docker run cloudflare/cloudflared:latest tunnel --no-autoupdate run --token xxxxxxxxxxxxxxxxxxxxxxxxxxx
```

её нужно немного видоизменить на следующую:

```bash
docker run -d \
  --name cloudflared-webhook \
  --restart unless-stopped \
  --network host \
  cloudflare/cloudflared:latest \
  tunnel --no-autoupdate run --token xxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Продолжаем настройку туннеля: после выбора Docker нужно нажать на `Next`. В правом нижнем углу откроется панель **Route
Traffic**, где необходимо привязать туннель к доменному имени. В subdomain прописываем, например, `mytunnel`, выбираем
домен. Path оставляем пустой (также сюда можно прописать полный, либо частичный путь до вебхука, чтобы отрезать лишние
запросы из интернета).

> **Очень важно!** В Service -> Type указываем **HTTP**, а не HTTPS! В URL указываем `127.0.0.1:<любой порт выше 2000>`.
> Можно указать тот же `8000` на котором работает приложение.

Заходим на сервер, устанавливаем Docker (если еще не) и в терминале вводим команду выше. Скачается образ и
запустится контейнер. В него можно зайти и посмотреть логи:

```bash
docker logs <имя контейнера> --tail 100
```

Проверьте, чтобы в нем не было ошибок подключения. А также проверьте статус туннеля в `Zero Trust` -> `Networks` ->
`Connectors`: туннель должен быть Healthy.

Последний шаг. Заходим в локальную консоль и набираем команду:

```bash
ssh -N -i <путь до SSH-ключа> -R 8000:0.0.0.0:8000 <login>@<server ip>
```

Измените первый порт на тот, что вы указывали в Cloudflare!

Теперь, до тех пор пока работает ssh-туннель, все запросы будут приходить на вашу локальную машину.

> **Примечание для стран, где не заблокирован Cloudflare**: вы можете выполнить первый шаг настройки доменного
> имени и вместо использования сервера, воспользоваться дефолтной командой у себя на локальной машине:
> ```bash
> docker run cloudflare/cloudflared:latest tunnel --no-autoupdate run --token xxxxxxxxxxxxxxxxxxxxxxxxxxx
> ```

## 6. Возможные проблемы

1. **Ошибки mypy**: если столкнулись с нестандартным поведением mypy (ошибки, нехарактерные для проекта), первым делом
   удалите папку `mypy_checks`. Это директория с кешами mypy, и иногда проблемы могут возникать из-за неё.

2. **Проблемы с подключением к PostgreSQL**: убедитесь, что сервер PostgreSQL доступен на порту `5432`. Это может быть
   как
   локальный сервер, так и контейнер в Docker.

3. **Именование модулей с тестами**: модули с тестами следует называть с постфиксом `test` (например, `client_test`, а
   не `test_client`). Это нужно для того, чтобы проходила проверка на корректность имён файлов в pre-commit. При этом
   сами тесты должны начинаться с префикса `test_` (например, `test_webhook`).

4. Если `docker buildx bake -f docker-bake.hcl` выдает ошибку, проверьте версию Docker. Она должна быть не ниже 29.1.5
