"""
Defines the abstract class for file managers

A file manager is responsible for taking input files and persisting them with unique identifiers
"""

from uuid import uuid4

from abc import ABC, abstractmethod

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from jserver.config import Config

class FileManager(ABC):
    @abstractmethod
    def __init__(self, config: 'Config'):
        raise NotImplementedError

    def create_data_uuid(self):
        """
        Creates a data UUID
        """
        return str(uuid4())

    @abstractmethod
    def insert_file(self, local_path: str) -> str:
        """
        Inserts a file into the file store and returns the file ID
        """
        raise NotImplementedError

    @abstractmethod
    def delete_file(self, file_id: str):
        """
        Deletes a file from the file store
        """
        raise NotImplementedError

    @abstractmethod
    def pull_file(self, file_id: str, local_path: str):
        """
        Copies a file from the file store to the local path

        Raises a FileDataNotFoundException if the file does not exist
        """
        raise NotImplementedError

    @abstractmethod
    def get_file_url(self, file_id: str) -> str:
        """
        Returns a url that can be used to access the file over http
        """
        raise NotImplementedError

    def get_file_urls(self, file_ids: list[str]) -> list[str]:
        """
        Returns a list of urls that can be used to access the files over http
        """
        return [self.get_file_url(file_id) for file_id in file_ids]
