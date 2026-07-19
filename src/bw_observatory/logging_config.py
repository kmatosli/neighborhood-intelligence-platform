"""Logging for ingestion runs.

Three log files, because they answer three different questions after a failed run:
`download.log` (what the pipeline did), `api.log` (what the portal returned), and
`validation.log` (what the data looked like).
"""

from __future__ import annotations

import logging
from pathlib import Path

DOWNLOAD_LOGGER = "bw_observatory.download"
API_LOGGER = "bw_observatory.api"
VALIDATION_LOGGER = "bw_observatory.validation"

_LOG_FILES = {
    DOWNLOAD_LOGGER: "download.log",
    API_LOGGER: "api.log",
    VALIDATION_LOGGER: "validation.log",
}

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s %(message)s"


def configure_logging(log_dir: Path, level: str = "INFO", console: bool = True) -> None:
    """Attach a file handler per logger, plus one shared console handler.

    Safe to call more than once; existing handlers are replaced rather than stacked.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(_FORMAT)

    console_handler: logging.Handler | None = None
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

    for name, filename in _LOG_FILES.items():
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.propagate = False

        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

        file_handler = logging.FileHandler(log_dir / filename, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        if console_handler is not None:
            logger.addHandler(console_handler)


def download_logger() -> logging.Logger:
    return logging.getLogger(DOWNLOAD_LOGGER)


def api_logger() -> logging.Logger:
    return logging.getLogger(API_LOGGER)


def validation_logger() -> logging.Logger:
    return logging.getLogger(VALIDATION_LOGGER)
