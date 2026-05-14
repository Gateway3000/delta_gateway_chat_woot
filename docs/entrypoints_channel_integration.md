# Подключение Channel через entry points

## Назначение

Это схема интеграции каналов в Gateway. Канал подключается как Python-plugin через `entry points` и загружается через
`ChannelRegistry.discover_channels(...)`.

## Минимальные требования

1. Реализовать контракт `IChannel` из `src/multichannel_gateway/core/interfaces/channel.py`
2. Экспортировать готовый объект канала (instance), у которого заполнено поле `channel`.
3. Добавить entry point в `pyproject.toml` пакета адаптера.

## Шаг 1. Создайте wiring модуля адаптера

Пример структуры:

- `channels/my_channel/my_wiring.py`
- `channels/my_channel/my_channel.py`

В `my_wiring.py` должен быть создан объект канала:

```python
from channels.my_channel.my_channel import MyChannel

my_channel = MyChannel(...)
```

Важно: entry point должен указывать именно на готовый instance, а не на класс.

## Шаг 2. Зарегистрируйте entry point

В `pyproject.toml` адаптера:

```toml
[project.entry-points."multichannel_gateway.channels"]
my_channel = "channels.my_channel.my_wiring:my_channel"
```

Где:

- `my_channel` (слева) — имя plugin entry;
- `channels.my_channel.my_wiring:my_channel` — путь к instance.

## Шаг 3. Установите пакет адаптера в окружение Gateway

Gateway увидит adapter только если пакет установлен в то же Python-окружение, где запускается приложение.

## Шаг 4. Убедитесь, что discovery включен

В точке входа Gateway должен вызываться:

```python
registry.discover_channels("multichannel_gateway.channels")
```

`discover_channels(...)` должен вызываться до старта приложения (до `registry.on_startup()`).

## Шаг 5. Настройте переменную окружения `CHANNELS`

Переменная `CHANNELS` определяет, какие каналы должны быть загружены из доступных entry points.

**Правильные форматы записи:**

```bash
# JSON-массив (рекомендуется)
CHANNELS='["Telegram", "Email"]'

# Python-синтаксис списка
CHANNELS=["Telegram"]

# Несколько каналов через запятую
CHANNELS="Telegram", "Email"
```

**Неправильный формат (приведет к ошибке валидации):**

```bash
# НЕПРАВИЛЬНО: одиночное значение без массива
CHANNELS="Telegram"
```

Если `CHANNELS` не задана или пуста, будут загружены все обнаруженные каналы.

## Поведение `ChannelRegistry.discover_channels(...)`

Если не найдено ни одного канала, гейтвей поднимет `RuntimeError` (работа без каналов не имеет практического смысла)

## Быстрая проверка

Проверьте, что entry point виден:

```bash
uv run python -c "from importlib.metadata import entry_points; print([f'{e.name}={e.value}' for e in entry_points().select(group='multichannel_gateway.channels')])"
```

## Ограничения этого подхода

- Адаптер работает в одном процессе вместе с Gateway.
- Зависимости адаптера попадают в окружение Gateway.
