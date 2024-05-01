"""
Defines a singleton class that manages input handlers

It takes a the input handler configuration and constructs the necessary input handlers from it
Also creates the file system directories for the input handlers
Creates the database connections for those input handlers that use persistent storage
"""

from pathlib import Path
import os
import asyncio
import time
import traceback

from jserver.config import Config, AllInputHandlerConfig
from jserver.storage import ResourceManager
from .handler_types import construct_input_handler
from .input_handler import EntryInsertionLog, InputHandler
from jserver.exceptions import *

from jserver.utils.logger import setup_logging
logger = setup_logging(__name__)

class InputHandlerManager:
    _instance = None

    @classmethod
    def construct_manager(cls, config):
        """
        Constructs the singleton instance of the InputHandlerManager class
        """
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(InputHandlerManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, config=None):
        # To avoid reinitialization of already initialized singleton instance
        if hasattr(self, 'is_initialized') and self.is_initialized:
            return
        assert config is not None, "InputHandlerManager requires a Config object"

        input_handler_config = config.input_config
        input_folder = input_handler_config.input_dir
        input_handler_configs = input_handler_config.input_handlers

        self.sleep_interval = 0.5  # The interval at which the input handler manager checks for periodic triggers

        self.input_folder = Path(input_folder)

        self.rmanager = ResourceManager()
        self.currently_processing_files = set()  # Set of files that are currently being processed

        self.input_handlers: dict[str, InputHandler] = {}  # Maps from handler_id to the input handler object
        self.handler_configs: dict[str, AllInputHandlerConfig] = {}  # Maps from handler_id to the handler config
        self.check_intervals: dict[str, float] = {}  # Maps from handler_id to the check interval for that handler
        self.last_updated: dict[str, int] = {}
        self.trigger_errors: dict[str, list[tuple[int, Exception]]] = {}  # Maps from handler_id to a list of exceptions that occurred during the trigger and the time they occurred
        self.construct_input_handlers(input_handler_configs)
        self.construct_input_folders()

        self.stop_event = asyncio.Event()
        self.watch_task = None

        # Flag to indicate the instance is fully initialized
        self.is_initialized = True

    def get_handler_info(self):
        """
        Returns serialized configuration about each handler as well as serialized exceptions
        """
        handler_info = {}
        for handler_id, handler in self.input_handlers.items():
            handler_info[handler_id] = {
                "config": self.handler_configs[handler_id].model_dump(),
                "trigger_errors": [(time, str(e)) for time, e in self.trigger_errors[handler_id]],
                "input_folder": str((self.input_folder / handler_id).absolute()) if handler._requires_input_folder else None,
                "handler_state": handler.get_state(),
                "takes_file_input": handler._takes_file_input,
            }
        return handler_info

    def construct_input_handlers(self, input_handler_configs: list[AllInputHandlerConfig]):
        for handler_config in input_handler_configs:
            logger.debug(f"Constructing input handler {handler_config.handler_name} - {handler_config.handler_uuid}")
            handler_id = handler_config.handler_uuid
            handler_name = handler_config.handler_name
            trigger_interval = handler_config.trigger_check_interval

            # Force capture of the handler_id in the lambda by using a default argument (Apparently this is the official method https://stackoverflow.com/a/2295372)
            on_entries_inserted_cb = lambda entry_insertion_log, handler_id=handler_id: self._on_entries_inserted(handler_id, entry_insertion_log)
            handler_obj = construct_input_handler(handler_config, on_entries_inserted_cb)

            if handler_obj._requires_db_connection:
                logger.info(f"Setting up database connection for input handler {handler_id}")
                handler_obj.set_db_connection(self.get_db_connection(handler_id))

            self.input_handlers[handler_id] = handler_obj
            self.handler_configs[handler_id] = handler_config
            self.trigger_errors[handler_id] = []
            self.check_intervals[handler_id] = trigger_interval
            self.last_updated[handler_id] = -1

    def get_db_connection(self, handler_id: str):
        """
        Returns the database connection for the given handler_id
        """
        return self.rmanager.get_database_connection(f"input_handler_{handler_id}")

    def construct_input_folders(self):
        """
        When any file is placed in these folders, the corresponding input handler is triggered
        """
        self.input_folder.mkdir(parents=True, exist_ok=True)
        for handler_id, handler_obj in self.input_handlers.items():
            if not handler_obj._requires_input_folder:
                continue
            handler_folder = self.input_folder / handler_id
            logger.debug(f"Creating folder for input handler {handler_id} - {handler_folder}")
            handler_folder.mkdir(parents=True, exist_ok=True)

    def _on_entries_inserted(self, handler_id: str, entry_insertion_log: list[EntryInsertionLog]):
        """
        Called by the input handler when entries are inserted into the database
        """
        if len(entry_insertion_log) == 0:
            logger.debug(f"Input handler {handler_id} did not insert any entries")
            return
        num_successful = sum(1 for log in entry_insertion_log if log.success)
        num_mutated = sum(1 for log in entry_insertion_log if log.mutated)
        num_failed = sum(1 for log in entry_insertion_log if not log.success)
        logger.info(f"Input handler {handler_id} inserted {num_successful} entries (mutated {num_mutated}) and failed {num_failed}")

    def record_trigger_error(self, handler_id: str, error: Exception):
        """
        Records an error that occurred while triggering the input handler
        """
        traceback_str = "".join(traceback.format_exception(type(error), value=error, tb=error.__traceback__))
        logger.error(f"Error while triggering handler {handler_id}:\n**************\n{traceback_str}\n**************")
        self.trigger_errors[handler_id].append((int(time.time() * 1000), error))

    async def start_file_trigger_watch(self, file_path: Path, handler_id: str):
        """
        Watches a file until it is stable and then triggers the handler

        Used when a new file appears in the input folder. Doing it this way ensures we do not
        prematurely trigger the handler while the file is still being written to
        """
        if file_path in self.currently_processing_files:
            return
        logger.info(f"Watching file {file_path} for handler {handler_id}")
        self.currently_processing_files.add(file_path)

        # Step 1: Wait until the file is stable
        last_size = 0
        size_stable = False
        while not (size_stable and can_open):
            can_open = False
            try:
                with open(file_path, "r") as f:
                    logger.debug(f"Opened file {file_path}")
                    can_open = True
            except Exception as e:
                logger.error(f"Error while reading file {file_path}: {e}")
                break

            cur_size = file_path.stat().st_size
            if cur_size == last_size:
                logger.debug(f"File {file_path} is stable")
                size_stable = True
            else:
                logger.debug(f"File {file_path} is not stable. Size changed from {last_size} to {cur_size}")
                last_size = cur_size

            await asyncio.sleep(0.5)
        logger.info(f"File {file_path} is stable. Triggering handler {handler_id}")

        # Step 2: Trigger the handler
        handler = self.input_handlers[handler_id]
        try:
            await handler.on_trigger_new_file(file_path)
        except Exception as e:
            self.record_trigger_error(handler_id, e)

        # Remove the file and remove it from the set of currently processing files
        file_path.unlink()
        self.currently_processing_files.remove(file_path)

    async def on_trigger_request(self, handler_id: str, file: str | None = None, metadata: dict[str, str] | None = None):
        """
        Called by the server when a request is received on POST /input_handlers/{handler_id}/request_trigger

        Triggers the input handler with the given handler_id
        Takes an optional file and metadata argument which is passed to the input handler
        """
        handler = self.input_handlers[handler_id]
        try:
            entry_insertion_log = await handler.on_trigger_request(file, metadata)
            return entry_insertion_log
        except Exception as e:
            self.record_trigger_error(handler_id, e)

    async def scan_input_dir(self):
        """
        Searches the input directory for files that are not in the currently processing files set
        For each, it calls the start_file_trigger_watch method so that the input handler is triggered
        when the file is stable
        """
        def scantree(path):
            """Recursively yield DirEntry objects for given directory."""
            for entry in os.scandir(path):
                if entry.is_dir(follow_symlinks=False):
                    yield from scantree(entry.path)
                else:
                    yield entry

        logger.debug(f"Scanning input directory {self.input_folder}")
        for dir_entry in scantree(self.input_folder):
            logger.debug(f"Found entry {dir_entry.path}")
            if not dir_entry.is_file():
                continue
            file_path = Path(dir_entry.path)
            if file_path in self.currently_processing_files:
                continue
            handler_id = file_path.parent.name
            # Create a new task to watch the file
            asyncio.create_task(self.start_file_trigger_watch(file_path, handler_id))

    async def interval_trigger_handler(self, handler_id: str):
        """
        Triggers the handler with the given handler_id
        """
        handler = self.input_handlers[handler_id]
        try:
            await handler.on_trigger_interval()
        except Exception as e:
            self.record_trigger_error(handler_id, e)

    async def _start_watching(self):
        """
        Starts the main loop that watches the input directory and triggers on the set intervals
        """
        logger.debug("Starting input handler manager")
        while not self.stop_event.is_set():
            time_ms = int(time.time() * 1000)
            logger.debug(f"Checking input handlers at {time_ms}")
            # First we check if we need to trigger any handlers based on the interval
            for handler_id, interval_seconds in self.check_intervals.items():
                if interval_seconds is None:
                    continue
                interval = interval_seconds * 1000
                if time_ms - self.last_updated[handler_id] > interval:
                    self.last_updated[handler_id] = time_ms
                    asyncio.create_task(self.interval_trigger_handler(handler_id))

            # Next we scan the input directory for new files
            asyncio.create_task(self.scan_input_dir())

            # Wait for the sleep interval or until the stop event is set
            try:
                await asyncio.wait_for(self.stop_event.wait(), self.sleep_interval)
            except asyncio.TimeoutError:
                # If we get a timeout error, we just continue because that means we did not get the stop event
                pass
        logger.debug("Stopped input handler manager")

    def handle_rpc_request(self, handler_id: str, rpc_name: str, data: dict):
        """
        Passes an RPC request to the correct input handler
        """
        if handler_id not in self.input_handlers:
            raise InputHandlerNotFoundException(f"Handler {handler_id} not found")
        handler = self.input_handlers[handler_id]
        rpc_map = handler._rpc_map
        if rpc_name not in rpc_map:
            raise RPCNameNotFoundException(f"RPC {rpc_name} not found in handler {handler_id}")
        rpc_func = rpc_map[rpc_name]
        return rpc_func(data)

    def start_watching(self):
        """
        Starts the main loop
        """
        self.watch_task = asyncio.create_task(self._start_watching())

    async def stop_watching(self):
        """
        Stops the main loop
        """
        self.stop_event.set()
        await self.watch_task




