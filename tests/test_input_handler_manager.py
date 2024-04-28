import pytest
import asyncio
import shutil
from pathlib import Path

from jserver.input_handlers import InputHandlerManager
from jserver.storage import ResourceManager
from jserver.storage.primitives import OutputFilter

from jserver.utils.logger import setup_logging
logger = setup_logging(__name__)

# @pytest.mark.asyncio
# async def test_input_handler_manager_creation(config):
#     InputHandlerManager.construct_manager(config)  # Create the singleton instance
#     input_handler_manager = InputHandlerManager()
#     handler_info = input_handler_manager.get_handler_info()
#     logger.info(f"Handler info: {handler_info}")
#     # Delete the singleton instance
#     InputHandlerManager._instance = None
#     input_handler_manager.is_initialized = False

@pytest.mark.asyncio
async def test_input_handler_manager_insert(input_handler_manager_gen, rmanager: ResourceManager):
    """
    Tests the start method of the input handler manager and waits for a bit to make sure it doesn't fail
    """
    input_handler_manager = await input_handler_manager_gen
    handler_info = input_handler_manager.get_handler_info()

    # We need to have the test input handler in the handler info for this test to work
    assert "test_input_handler" in handler_info, "Test input handler not found"

    await asyncio.sleep(1)  # Leave enough time for the interval trigger to run

    # Ensure that the test input handler inserted an entry
    output_filter = OutputFilter(
        entry_types=["text"],
        input_handler_ids=["test_input_handler"],
    )
    entries = rmanager.search_entries(output_filter)
    assert len(entries) > 0

@pytest.mark.asyncio
async def test_input_handler_file_input(test_files_dir, input_handler_manager_gen, rmanager: ResourceManager):
    """
    Tests the file input trigger of the test input handler

    Moves a test file into the input handler's directory and checks that the input handler picks it up
    """
    input_handler_manager = await input_handler_manager_gen
    handler_info = input_handler_manager.get_handler_info()

    # We need to have the test input handler in the handler info for this test to work
    assert "test_input_handler" in handler_info, "Test input handler not found"

    test_handler_input_folder = Path(handler_info["test_input_handler"]["input_folder"])
    logger.info(f"Test input handler folder: {test_handler_input_folder}")

    test_file = test_files_dir / "test_video.mp4"
    assert test_file.exists(), f"Test file not found: {test_file}"

    # Copy the test file into the input handler's folder
    test_text_file_dest = test_handler_input_folder / test_file.name
    shutil.copy(test_file, test_text_file_dest)
    assert test_text_file_dest.exists(), f"Test file not found in handler folder: {test_text_file_dest}"

    await asyncio.sleep(5)  # Leave enough time for the file trigger to run

    # Ensure that the test input handler inserted an entry
    output_filter = OutputFilter(
        entry_types=["text_file", "video_file"],
        input_handler_ids=["test_input_handler"],
    )
    entries = rmanager.search_entries(output_filter)
    assert len(entries) > 0


