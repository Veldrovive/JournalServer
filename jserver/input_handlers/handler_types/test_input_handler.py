from datetime import datetime
from pathlib import Path

from jserver.input_handlers.input_handler import InputHandler, EntryInsertionLog
from jserver.config.input_handler_config import TestInputHandlerConfig
from jserver.entries import TextEntry, TextFileEntry, VideoFileEntry

from jserver.utils.logger import setup_logging
logger = setup_logging(__name__)

from typing import Callable

class TestInputHandler(InputHandler):
    _requires_db_connection = True
    _requires_input_folder = True
    _takes_file_input = True

    def __init__(self, handler_id: str, config: TestInputHandlerConfig, on_entries_inserted: Callable[[list[EntryInsertionLog]], None]):
        super().__init__(handler_id, config, on_entries_inserted)
        self.config = config
        self.num_interval_entries = 0
        self.start_time = int(datetime.now().timestamp() * 1000)

    async def _on_trigger_request(self, entry_insertion_log: list[EntryInsertionLog], file: str | None = None, metadata: dict[str, str] | None = None):
        logger.info(f"Got a trigger request for test input handler {self.handler_id} with args {file}, {metadata}")

    async def _on_trigger_new_file(self, entry_insertion_log: list[EntryInsertionLog], file: str):
        logger.info(f"Got a new file trigger for test input handler {self.handler_id} with file {file}")
        file_path = Path(file)
        file_ext = file_path.suffix
        if file_ext == ".txt":
            file_detail = TextFileEntry.generate_file_detail(file, {})
            entry = TextFileEntry(
                data=file_detail,
                start_time=self.start_time,
                input_handler_id=self.handler_id,
                group_id="test_group",
                seq_id=0,
            )
            self.insert_file_entry(entry_insertion_log, entry)
        elif file_ext == ".mp4":
            file_detail = VideoFileEntry.generate_file_detail(file, {})
            entry = VideoFileEntry(
                data=file_detail,
                start_time=self.start_time,
                input_handler_id=self.handler_id,
                group_id="test_group",
                seq_id=0,
            )
            self.insert_file_entry(entry_insertion_log, entry)
        else:
            logger.error(f"Unsupported file extension for test input handler: {file_ext}")

    async def _on_trigger_interval(self, entry_insertion_log: list[EntryInsertionLog]):
        logger.debug(f"Got an interval trigger for test input handler {self.handler_id}")
        if self.num_interval_entries > 0:
            return
        # Creates a new text entry with the current time
        entry = TextEntry(
            data=f"Test entry at {datetime.now()}",
            start_time=self.start_time,
            input_handler_id=self.handler_id,
            group_id="test_group",
            seq_id=self.num_interval_entries,
        )
        self.insert_entry(entry_insertion_log, entry)
        self.num_interval_entries += 1

