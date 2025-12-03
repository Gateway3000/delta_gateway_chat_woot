from src.multichannel_gateway.app.di import registry
from src.multichannel_gateway.run import run
from telegram.dependencies import telegram_gateway

registry.register_gateway(telegram_gateway)

if __name__ == "__main__":
    run()
