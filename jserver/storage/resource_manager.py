"""
Stores a singleton instance of the ResourceManager class, which is responsible for
managing connections to the database and file store.
"""

from contextlib import contextmanager
from tempfile import NamedTemporaryFile
import os
import time

from jserver.storage.file import FileManager
from jserver.storage.db import DatabaseManager
from jserver.storage.primitives import OutputFilter

from jserver.utils.logger import setup_logging
logger = setup_logging(__name__)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from jserver.config import Config
    from jserver.entries import Entry
    from jserver.entries.primitives import EntryUUID

class ResourceManager:
    _instance = None
    _db: DatabaseManager
    _file_store: FileManager

    @classmethod
    def construct_manager(cls, db, file_store):
        """
        Constructs the singleton instance of the ResourceManager class
        """
        if cls._instance is None:
            cls._instance = cls()
            cls._instance.set_db(db)
            cls._instance.set_file_store(file_store)
        return cls._instance

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ResourceManager, cls).__new__(cls)
        return cls._instance

    def set_db(self, db: DatabaseManager):
        self._db = db

    def set_file_store(self, file_store: FileManager):
        self._file_store = file_store

    ########## File Store Management ##########
    @contextmanager
    def get_temp_local_file(self, file_id):
        """
        Pulls a file from the file store to a local file
        When the context manager returns, the file is deleted
        """
        with NamedTemporaryFile(delete=False) as temp_file:
            self._file_store.pull_file(file_id, temp_file.name)
            yield temp_file.name
            os.remove(temp_file.name)

    def get_file_url(self, file_id):
        """
        Returns a URL for the file
        """
        return self._file_store.get_file_url(file_id)

    def insert_file(self, file_path):
        """
        Uploads a file to the file store
        """
        return self._file_store.insert_file(file_path)

    def delete_file(self, file_id):
        """
        Deletes a file from the file store
        """
        self._file_store.delete_file(file_id)

    def pull_file(self, file_id, local_path):
        """
        Pulls a file from the file store to a local path
        """
        self._file_store.pull_file(file_id, local_path)
    ############################################

    ########### Database Management ############
    def get_database_connection(self, db_name: str):
        """
        Returns a connection to the database with the given name
        """
        return self._db.get_database_connection(db_name)

    def insert_entry(self, entry: 'Entry'):
        """
        Inserts an entry into the database
        """
        self._db.insert_entry(entry)

    def delete_entry(self, entry_id: 'EntryUUID'):
        """
        Deletes an entry from the database
        """
        self._db.delete_entry(entry_id)

    def pull_entry(self, entry_id: 'EntryUUID'):
        """
        Pulls an entry from the database
        """
        return self._db.pull_entry(entry_id)

    def pull_entries(self, entry_ids: list['EntryUUID']):
        """
        Pulls multiple entries from the database
        """
        start_time = time.time()
        res = self._db.pull_entries(entry_ids)
        logger.info(f"Pull took {time.time() - start_time} seconds to read {len(entry_ids)} entries")
        return res

    def search_entries(self, filter: OutputFilter) -> list['EntryUUID']:
        """
        Searches for entries in the database
        """
        start_time = time.time()
        res = self._db.search_entries(filter)
        logger.info(f"Search took {time.time() - start_time} seconds to find {len(res)} entries")
        return res
    ############################################
