"""
Main entrypoint for the jserver package

Responsible for checking python >= 3.10, and starting the server

Creates the connections to the database and file store by constructing the ResourceManager
Creates the InputHandlerManager singleton instance
"""

import sys
import asyncio

from jserver.config import Config
from jserver.storage import construct_manager as construct_resource_manager
from jserver.utils.config import load_config
from jserver.input_handlers import InputHandlerManager
from jserver.server import start_server

from jserver.utils.logger import setup_logging
logger = setup_logging(__name__)

def check_version():
    """
    Checks that the python version is >= 3.10
    """
    if sys.version_info < (3, 10):
        raise ValueError("Python >= 3.10 is required")

def construct_managers(config: Config):
    """
    Constructs the singleton instance of the ResourceManager class

    This ensures that we can connect to both the database and file store
    """
    logger.info("Constructing resource manager")
    construct_resource_manager(config)
    logger.info("Constructing input handler manager")
    InputHandlerManager.construct_manager(config)  # Note that this does not start the watcher. start_watching still needs to be called.

async def main(config: Config):
    """
    Main entrypoint for the jserver package
    """
    logger.info("Checking python version")
    check_version()

    logger.info("Constructing managers")
    construct_managers(config)

    logger.info("Starting server")
    logger.debug(f"Starting server with config: {config}")

    input_handler_manager = InputHandlerManager()  # Get a reference to the singleton instance
    logger.info("Starting input handler watcher")
    input_handler_manager.start_watching()
    logger.info("Starting server")
    server_task = asyncio.create_task(start_server(config))

    try:
        await server_task
    except KeyboardInterrupt:
        logger.info("Stopping server")
        await server_task
        logger.info("Stopping input handler watcher")
        input_handler_manager.stop_watching()

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Start the journaling server")
    # --config-path or -c: The path to the config file
    parser.add_argument("--config-path", "-c", type=str, required=False, help="The path to the config file")

    args = parser.parse_args()
    config = load_config(args.config_path)

    asyncio.run(main(config))
