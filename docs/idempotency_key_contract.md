# Контракт ключей идемпотентности каналов

## Назначение документа

Документ фиксирует единый контракт формирования ключей идемпотентности для всех каналов. Описывает интерфейс `IEnvelopeFactory`, обязательные поля и правила хеширования.

## Содержание

- [Общий контракт](#общий-контракт)
- [Обязательные поля](#обязательные-поля)
- [Хеширование](#хеширование)
- [Пример реализации для нового канала](#пример-реализации-для-нового-канала)
- [Почему extra хешируется](#почему-extra-хешируется)

---

## Общий контракт

В проекте используется `IEnvelopeFactory` (`src/multichannel_gateway/core/interfaces/envelope_factory.py`) для генерации ключей идемпотентности.

Метод `build_idempotency_key()` формирует ключ в унифицированном формате:

```
{direction}:{connector_id}:{extra_hash}:{external_id_hash}:{message_id_hash}
```

Все каналы обязаны наследоваться от `IEnvelopeFactory` и использовать этот метод вместо собственной логики формирования ключей.

---

## Обязательные поля

Для генерации ключа требуются:

| Поле | Тип | Описание |
|------|-----|----------|
| `direction` | `str` | Направление сообщения, например `telegram->chatwoot` или `chatwoot->telegram` |
| `connector_id` | `str` | ID коннектора из маршрута |
| `external_id` | `str` | ID отправителя в канале (обязательно, не пустое) |
| `message_id` | `str` | ID сообщения в канале (обязательно, не пустое) |

При отсутствии `external_id` или `message_id` метод выбрасывает `ValueError`.

Специфичные для канала параметры передаются через `**extra`.

---

## Хеширование

Для унификации и сокращения длины ключа все переменные части хешируются:

- Алгоритм: `sha1`
- Длина хеша: 12 символов (первые 12 символов hexdigest)
- `extra` сортируется по ключам перед хешированием для детерминированности
- Если `extra` пуст, используется хеш-заглушка `000000000000`

Пример:
```python
extra = {"bot_token_suffix": "12345", "chat_id": "111"}
# Сортируется: bot_token_suffix=12345, chat_id=111
# Хешируется строка: "bot_token_suffix=12345:chat_id=111"
```

---

## Пример реализации для нового канала

При добавлении нового канала:

1. Унаследуйте фабрику от `IEnvelopeFactory`.
2. Используйте `self.build_idempotency_key()` для генерации ключей.
3. Передавайте обязательные поля и специфичные параметры через `**extra`.

Пример для гипотетического канала:

```python
from src.multichannel_gateway.core.interfaces.envelope_factory import IEnvelopeFactory


class NewChannelEnvelopeFactory(IEnvelopeFactory):
    def parse_channel_request(self, raw_data, connector_id, channel):
        route = self._routing.get_route_by_connector_id(connector_id)
        external_id = raw_data["user"]["id"]
        message_id = raw_data["message"]["id"]

        idem_key = self.build_idempotency_key(
            direction=f"{channel}->chatwoot",
            connector_id=route["connector_id"],
            external_id=external_id,
            message_id=message_id,
            platform_thread_id=raw_data.get("thread_id", ""),
        )

        # ... создание Envelope
        return idem_key, envelope
```

---

## Почему extra хешируется

Специфичные параметры каналов (токены, mailbox, uid) могут быть длинными или содержать чувствительные данные.

Хеширование решает две задачи:

1. **Унификация длины ключа** — ключ имеет предсказуемый формат независимо от количества и длины extra-полей.
2. **Безопасность** — чувствительные части (например, фрагменты токенов) не попадают в ключ в открытом виде.

Это гарантирует, что новые каналы не смогут случайно сформировать ненадежный ключ, если забудут про достаточную энтропию.
