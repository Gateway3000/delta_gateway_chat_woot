from src.multichannel_gateway.app.wiring import registry, settings
from src.multichannel_gateway.run import run

registry.discover_channels("multichannel_gateway.channels", settings.channels)

if __name__ == "__main__":
    run()
