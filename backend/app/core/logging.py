import logging


def setup_logging(log_level="INFO", environment="development"):
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


def get_logger(name: str):
    return logging.getLogger(name)