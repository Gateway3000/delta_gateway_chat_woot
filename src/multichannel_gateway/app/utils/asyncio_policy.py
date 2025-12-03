import asyncio
import sys


def check_eventloop_policy() -> None:
    """Sets the appropriate asyncio event loop policy for Windows systems.

    This function ensures compatibility with asyncio on Windows by explicitly
    setting the `WindowsSelectorEventLoopPolicy`, which prevents runtime errors
    when using certain asynchronous frameworks or libraries.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
