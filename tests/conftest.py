import pytest
import os
from pathlib import Path
import subprocess
from uuid import uuid4
import asyncio
import time

from jserver.utils.config import load_config
from jserver.storage import construct_manager, ResourceManager
from jserver.entries import validate_entry
from jserver.entries.primitives import EntryType, EntryPrivacy
from jserver.input_handlers import InputHandlerManager

from jserver.utils.logger import setup_logging
logger = setup_logging(__name__)

cwd = Path(__file__).parent

config_path = cwd / "config.yml"
assert config_path.exists(), f"Config file not found: {config_path}"
os.environ["JSERVER_CONFIG_PATH"] = config_path.absolute().as_posix()

docker_compose_path = cwd / "docker-compose.yml"
assert docker_compose_path.exists(), f"Docker Compose file not found: {docker_compose_path}"
docker_compose_abs_path = docker_compose_path.absolute().as_posix()

test_files_path = cwd / "files"

@pytest.fixture(scope="session", autouse=True)
def start_docker_containers():
    """
    Starts the docker containers for the database and file storage
    Uses subprocess to first run `docker compose down -v -f {docker_compose_path}` to kill the existing containers and remove the volumes
    Then runs `docker compose up -d -f {docker_compose_path}` to start the containers in the background
    This way we can inspect the final state after the test finishes since we do not remove the volumes after
    """
    command_args = ["docker", "compose", "-f", docker_compose_abs_path, "down", "-v"]
    subprocess.run(command_args)

    command_args = ["docker", "compose", "-f", docker_compose_abs_path, "up", "-d"]
    subprocess.run(command_args)

@pytest.fixture(scope="session")
def config():
    return load_config()

@pytest.fixture(scope="session", autouse=True)
def rmanager(config, start_docker_containers):
    return construct_manager(config)

@pytest.fixture()
def test_files_dir():
    return test_files_path

@pytest.fixture(scope="session")
def session_test_text_entry():
    current_time = int(time.time() * 1000)
    entry_data = {
        "entry_type": EntryType.TEXT,
        "data": "Hello, World!",
        "privacy": EntryPrivacy.PUBLIC,
        "start_time": current_time - 1000,
        "end_time": current_time + 10000,
        "latitude": 1.0,
        "longitude": 0.1,
        "height": 1.0,
        "group_id": "dummy_group",
        "seq_id": 0,
        "input_handler_id": "dummy_input_handler",
        "tags": ["spicy", "tame"]
    }
    return validate_entry(entry_data)

@pytest.fixture(scope="session")
def session_test_text_file_id(rmanager: ResourceManager):
    test_file_path = test_files_path / "test_text.txt"
    assert test_file_path.exists(), f"Test file not found: {test_file_path}"
    # Upload the file to the file store
    file_id = rmanager.insert_file(test_file_path)
    yield file_id
    # Clean up the file store
    rmanager.delete_file(file_id)

@pytest.fixture(scope="session")
def session_test_generic_file_entry(session_test_text_file_id):
    current_time = int(time.time() * 1000)
    entry_data = {
        "entry_type": EntryType.GENERIC_FILE,
        "data": {
            "file_id": session_test_text_file_id,
            "file_name": "test_text.txt",
            "file_type": "txt",
            "file_metadata": {}
        },
        "privacy": EntryPrivacy.PUBLIC,
        "start_time": current_time - 1000,
        "end_time": current_time + 10000,
        "latitude": 1.0,
        "longitude": 0.1,
        "height": 1.0,
        "group_id": "dummy_group",
        "seq_id": 0,
        "input_handler_id": "dummy_input_handler",
        "tags": ["spicy", "tame"]
    }
    return validate_entry(entry_data)

@pytest.fixture(scope="session", autouse=True)
async def construct_input_handler_manager(rmanager, config):
    InputHandlerManager.construct_manager(config)
    imanager = InputHandlerManager()
    imanager.start_watching()

@pytest.fixture(scope="function")
async def input_handler_manager_gen(construct_input_handler_manager, config, rmanager):
    try:
        await construct_input_handler_manager
    except Exception as e:
        pass
    imanager = InputHandlerManager()

    return imanager
