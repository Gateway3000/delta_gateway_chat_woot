import logging

from src.multichannel_gateway.app import TelemetrySettings


def setup_sentry(settings: TelemetrySettings) -> None:
    if not settings.otel_enabled or not settings.sentry_dsn:
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.otlp import OTLPIntegration
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Sentry is enabled but sentry-sdk is not installed. "
            "Install optional dependency: sentry-sdk[opentelemetry-otlp]."
        ) from exc

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment.value,
        release=settings.sentry_release,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=settings.sentry_send_default_pii,
        debug=False,
        default_integrations=True,
        auto_enabling_integrations=False,
        enable_logs=True,
        shutdown_timeout=1.0,
        instrumenter="otel" if settings.otel_enabled else "sentry",
        integrations=[
            OTLPIntegration(),
            LoggingIntegration(
                level=logging.INFO,
                event_level=logging.ERROR,
                sentry_logs_level=logging.INFO,
            ),
        ],
    )
