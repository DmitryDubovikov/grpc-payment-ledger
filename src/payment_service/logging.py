import logging
import sys
from typing import Literal

import structlog


def configure_logging(
    level: str = "INFO",
    log_format: Literal["json", "console"] = "json",
) -> None:
    timestamper = structlog.processors.TimeStamper(fmt="iso")

    shared_processors: list[structlog.typing.Processor] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.contextvars.merge_contextvars,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        timestamper,
    ]

    if log_format == "json":
        renderer: structlog.typing.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, level.upper()))

    for logger_name in ["sqlalchemy", "grpc", "asyncio"]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
