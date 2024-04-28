"""
These tests
"""

import pytest
import asyncio
import shutil
from pathlib import Path

from jserver.input_handlers import InputHandlerManager
from jserver.storage import ResourceManager
from jserver.storage.primitives import OutputFilter

from jserver.utils.logger import setup_logging
logger = setup_logging(__name__)

@pytest.mark.asyncio
async def test_day_one_handler_present(input_handler_manager_gen):
    async for input_handler_manager in input_handler_manager_gen:
        handler_info = input_handler_manager.get_handler_info()
        assert "day_one_handler" in handler_info, "Day One handler not found"

@pytest.mark.asyncio
async def test_day_one_file_trigger(input_handler_manager_gen, test_files_dir: Path, rmanager: ResourceManager):
    """
    The day one input handler has a file trigger registered for .zip files
    """
    async for input_handler_manager in input_handler_manager_gen:
        handler_info = input_handler_manager.get_handler_info()
        day_one_input_path = Path(handler_info["day_one_handler"]["input_folder"])
        assert day_one_input_path.is_dir(), f"Day One input folder does not exist: {day_one_input_path}"

        day_one_input_zip_path = test_files_dir / "inputs" / "day_one" / "day_one_sample.zip"
        assert day_one_input_zip_path.exists(), f"Day One input file not found: {day_one_input_zip_path}"

        # Copy the test file into the input handler's folder
        day_one_input_zip_dest = day_one_input_path / day_one_input_zip_path.name
        shutil.copy(day_one_input_zip_path, day_one_input_zip_dest)

        await asyncio.sleep(5)  # Leave enough time for the file trigger to run

        # Ensure that we inserted 13 entries from the day one input handler
        # This is the number in the sample file. If it changes, this test will need to be updated
        output_filter = OutputFilter(
            input_handler_ids=["day_one_handler"],
        )
        entries = rmanager.search_entries(output_filter)
        assert len(entries) == 13

# @pytest.mark.asyncio
# async def test_day_one_request_trigger(input_handler_manager_gen, test_files_dir: Path, rmanager: ResourceManager):
