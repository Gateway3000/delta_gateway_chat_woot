from collections.abc import Mapping
from typing import Any

from opentelemetry import propagate
from opentelemetry.context import Context

TRACE_CONTEXT_KEY = "_otel_trace_context"


def inject_trace_context(payload: Mapping[str, Any]) -> dict[str, Any]:
    enriched_payload = dict(payload)
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    if carrier:
        enriched_payload[TRACE_CONTEXT_KEY] = carrier
    return enriched_payload


def extract_trace_context(
    payload: Mapping[str, Any],
) -> tuple[Context | None, dict[str, Any]]:
    enriched_payload = dict(payload)
    carrier = enriched_payload.pop(TRACE_CONTEXT_KEY, None)
    if not isinstance(carrier, dict):
        return None, enriched_payload

    normalized_carrier = {
        str(key): str(value) for key, value in carrier.items() if value is not None
    }
    if not normalized_carrier:
        return None, enriched_payload

    return propagate.extract(normalized_carrier), enriched_payload
