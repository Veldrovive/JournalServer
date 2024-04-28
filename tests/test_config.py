from jserver.utils.logger import setup_logging
logger = setup_logging(__name__)

def test_load_config(config):
    logger.debug(f"\nConfig:\n{config.model_dump_json(indent=2)}")
