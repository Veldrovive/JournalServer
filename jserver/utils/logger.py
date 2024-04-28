import logging
import os

def setup_logging(name_override=None):
    # This sets up the root logger
    log_level_str = os.environ.get('LOG_LEVEL', 'INFO').upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    logging.basicConfig(level=log_level)

    # If you want a specific logger for your module or library
    logger = logging.getLogger(__name__ if name_override is None else name_override)
    return logger