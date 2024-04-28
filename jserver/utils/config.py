from pathlib import Path
import yaml
import os

from jserver.config import Config

from jserver.utils.logger import setup_logging
logger = setup_logging(__name__)

def load_config(config_path: str | None = None) -> Config:
    """
    Loads the config from the given path
    """
    if config_path is None:
        # Then we take the environment variable JSERVER_CONFIG_PATH
        config_path = os.getenv("JSERVER_CONFIG_PATH")
    if config_path is None:
        raise ValueError("No config path provided. Please provide a path to the config file with --config-path or set the JSERVER_CONFIG_PATH environment variable.")

    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        config_data = yaml.safe_load(f)
    # logger.info(f"Loaded config from {config_path}: {config_data}")
    return Config.model_validate(config_data)
