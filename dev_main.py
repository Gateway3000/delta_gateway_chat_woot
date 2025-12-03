from src.multichannel_gateway.app.di import registry
from src.multichannel_gateway.dev_run import dev_run
from telegram.dependencies import telegram_gateway

registry.register_gateway(telegram_gateway)

if __name__ == "__main__":
    dev_run()
