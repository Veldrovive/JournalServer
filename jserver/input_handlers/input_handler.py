"""
Defines the abstract class for an input handler
"""

from abc import ABC, abstractmethod
from pydantic import BaseModel
import asyncio
import traceback

from jserver.entries import Entry, GenericFileEntry
from jserver.entries.primitives import EntryUUID
from jserver.storage import EntryManager
from jserver.config.input_handler_config import AllInputHandlerConfig

from jserver.utils.logger import setup_logging
logger = setup_logging(__name__)

from typing import Callable

class EntryInsertionLog(BaseModel):
    """
    A log of the entries that were inserted into the database
    """
    entry_uuid: EntryUUID
    entry: Entry
    success: bool
    mutated: bool  # True if the entry already existed and was updated
    error: str | None

class InputHandler(ABC):
    _requires_db_connection = False
    _requires_input_folder = False
    _takes_file_input = False

    def __init__(
        self,
        handler_id: str,
        config: AllInputHandlerConfig,
        on_entries_inserted: Callable[[list[EntryInsertionLog]], None],
    ):
        self.handler_id = handler_id
        self.config = config
        self.on_entries_inserted = on_entries_inserted
        self.db_connection = None

        self.emanager = EntryManager()

    def set_db_connection(self, db_connection):
        self.db_connection = db_connection

    def insert_entry(self, entry_insertion_log: list[EntryInsertionLog], entry: Entry, mutate=True):
        """
        Helper function for inserting an entry and tracking the insertion
        """
        try:
            mutated = self.emanager.insert_entry(entry, mutate)
            entry_insertion_log.append(EntryInsertionLog(entry_uuid=entry.entry_uuid, entry=entry, success=True, mutated=mutated, error=None))
        except Exception as e:
            traceback_str = "".join(traceback.format_exception(type(e), value=e, tb=e.__traceback__))
            logger.error(f"Error inserting entry: {traceback_str}")
            entry_insertion_log.append(EntryInsertionLog(entry_uuid=entry.entry_uuid, entry=entry, success=False, mutated=False, error=str(e)))

    def insert_file_entry(self, entry_insertion_log: list[EntryInsertionLog], file_entry: GenericFileEntry, mutate=True):
        """
        Helper function for inserting a file entry and tracking the insertion
        """
        try:
            mutated = self.emanager.insert_file_entry(file_entry, mutate, delete_old_file=True)
            entry_insertion_log.append(EntryInsertionLog(entry_uuid=file_entry.entry_uuid, entry=file_entry, success=True, mutated=mutated, error=None))
        except Exception as e:
            traceback_str = "".join(traceback.format_exception(type(e), value=e, tb=e.__traceback__))
            logger.error(f"Error inserting file entry: {traceback_str}")
            entry_insertion_log.append(EntryInsertionLog(entry_uuid=file_entry.entry_uuid, entry=file_entry, success=False, mutated=False, error=str(e)))

    async def on_trigger_request(self, file: str | None = None, metadata: dict[str, str] | None = None) -> None:
        """
        Wrapper for the handler specific request trigger (Called on POST /input_handlers/{handler_id}/request_trigger)

        Injects the entry insertion log to keep track of what was inserted during this trigger
        """
        entry_insertion_log = []
        if not asyncio.iscoroutinefunction(self._on_trigger_request):
            raise ValueError("on_trigger_request must be a coroutine function")
        await self._on_trigger_request(entry_insertion_log, file, metadata)
        self.on_entries_inserted(entry_insertion_log)
        return entry_insertion_log

    async def on_trigger_new_file(self, file: str) -> None:
        """
        Wrapper for the handler specific new file trigger (Called when a new file is added to the input handler directory)

        Injects the entry insertion log to keep track of what was inserted during this trigger
        """
        entry_insertion_log = []
        if not asyncio.iscoroutinefunction(self._on_trigger_new_file):
            raise ValueError("on_trigger_new_file must be a coroutine function")
        await self._on_trigger_new_file(entry_insertion_log, file)
        self.on_entries_inserted(entry_insertion_log)

    async def on_trigger_interval(self) -> None:
        """
        Wrapper for the handler specific interval trigger (Called when the interval is reached)

        Injects the entry insertion log to keep track of what was inserted during this trigger
        """
        entry_insertion_log = []
        if not asyncio.iscoroutinefunction(self._on_trigger_interval):
            raise ValueError("on_trigger_interval must be a coroutine function")
        await self._on_trigger_interval(entry_insertion_log)
        self.on_entries_inserted(entry_insertion_log)

    @abstractmethod
    async def _on_trigger_request(self, entry_insertion_log: list[EntryInsertionLog], file: str | None = None, metadata: dict[str, str] | None = None) -> None:
        """
        Called when a request is received on POST /input_handlers/{handler_id}/request_trigger

        May optionally include a file and metadata
        """
        raise NotImplementedError

    @abstractmethod
    async def _on_trigger_new_file(self, entry_insertion_log: list[EntryInsertionLog], file: str) -> None:
        """
        Called when a new file is added to the input handler directory
        """
        raise NotImplementedError

    @abstractmethod
    async def _on_trigger_interval(self, entry_insertion_log: list[EntryInsertionLog]) -> None:
        """
        If the input handler is set to trigger on an interval, this is called when the interval is reached
        """
        raise NotImplementedError
