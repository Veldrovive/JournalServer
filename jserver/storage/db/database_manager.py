"""
Defines the abstract class for database managers

A database manager is responsible for persisting non-file data for entries
It receives an entry object, serializes it, and persists it in the database
It provides methods for querying different entry fields
It provides methods that use the entry id to retrieve the entry object
When returning objects, it deserializes them back into entry objects
"""

from abc import ABC, abstractmethod

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from jserver.config import Config
    from jserver.entries import Entry
    from jserver.entries.primitives import EntryUUID
    from jserver.storage.primitives import OutputFilter

class DatabaseManager(ABC):
    @abstractmethod
    def __init__(self, config: 'Config'):
        raise NotImplementedError

    @abstractmethod
    def get_database_connection(self, db_name: str):
        """
        Returns a connection to the database with the given name
        """
        raise NotImplementedError

    @abstractmethod
    def insert_entry(self, entry: 'Entry') -> None:
        """
        Inserts an entry into the database
        """
        raise NotImplementedError

    @abstractmethod
    def delete_entry(self, entry_id: 'EntryUUID') -> None:
        """
        Deletes an entry from the database
        """
        raise NotImplementedError

    @abstractmethod
    def pull_entry(self, entry_id: 'EntryUUID') -> 'Entry':
        """
        Pulls an entry from the database
        """
        raise NotImplementedError

    @abstractmethod
    def pull_entries(self, entry_ids: list['EntryUUID']) -> list['Entry']:
        """
        Pulls multiple entries from the database
        """
        raise NotImplementedError

    @abstractmethod
    def search_entries(self, query: 'OutputFilter') -> list['EntryUUID']:
        """
        Searches the database for entries that match the query
        """
        raise NotImplementedError
