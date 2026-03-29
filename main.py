from src.multichannel_gateway.app.wiring import registry
from src.multichannel_gateway.run import run
from telegram.tg_wiring import telegram_channel

registry.register_gateway(telegram_channel)

if __name__ == "__main__":
    run()
