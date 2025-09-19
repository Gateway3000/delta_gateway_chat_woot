import logging
import os
import sys


class ColoredFormatter(logging.Formatter):
    COLORS: dict[str, str] = {
        "DEBUG": "\033[94m",  # blue
        "INFO": "\033[92m",  # green
        "WARNING": "\033[93m",  # yellow
        "ERROR": "\033[31m",  # red
        "CRITICAL": "\033[95m",  # purple
    }
    RESET: str = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color: str = self.COLORS.get(record.levelname, self.RESET)
        message: str = super().format(record)
        return f"{color}{message}{self.RESET}"


class ExactLevelFilter(logging.Filter):
    def __init__(self, level: int):
        super().__init__()
        self.level = level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno == self.level


def setup_logger(
    name: str | None = None,
    level: int = logging.DEBUG,
    log_to_file: bool = False,
    warning_logfile: str = "logs/warning.log",
    error_logfile: str = "logs/error.log",
) -> logging.Logger:
    lg = logging.getLogger(name)
    lg.setLevel(level)

    if lg.handlers:
        return lg

    log_format = "[{asctime}] [{levelname:^8}] [{filename}:{lineno}] {message}"
    date_format = "%Y-%m-%d %H:%M:%S"

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(
        ColoredFormatter(fmt=log_format, style="{", datefmt=date_format)
    )
    lg.addHandler(console_handler)

    if log_to_file:
        os.makedirs(os.path.dirname(warning_logfile), exist_ok=True)
        os.makedirs(os.path.dirname(error_logfile), exist_ok=True)

        warning_handler = logging.FileHandler(warning_logfile, encoding="utf-8")
        warning_handler.setLevel(logging.WARNING)
        warning_handler.addFilter(ExactLevelFilter(logging.WARNING))
        warning_handler.setFormatter(
            logging.Formatter(fmt=log_format, style="{", datefmt=date_format)
        )
        lg.addHandler(warning_handler)

        error_handler = logging.FileHandler(error_logfile, encoding="utf-8")
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(
            logging.Formatter(fmt=log_format, style="{", datefmt=date_format)
        )
        lg.addHandler(error_handler)

    return lg


logger = setup_logger(__name__, log_to_file=True)
