"""
Utility class to manage inserting and updating entries in the database.
Also provides utilities for safely inserting file entries
"""

from jserver.storage import ResourceManager
from jserver.entries import Entry, GenericFileEntry
from jserver.entries.types.file_entries import *
from jserver.entries.primitives import EntryUUID
from jserver.storage.primitives import OutputFilter

from jserver.exceptions import *

class EntryManager:
    def __init__(self):
        self.rmanager = ResourceManager()

        self.deletion_map = {
            EntryType.TEXT: self.delete_non_file_entry,  # Used when deleting the database entry is enough
            EntryType.GENERIC_FILE: self.delete_file_entry,  # Also deles the file from the file store
            EntryType.TEXT_FILE: self.delete_file_entry,
            EntryType.IMAGE_FILE: self.delete_file_entry,
            EntryType.VIDEO_FILE: self.delete_file_entry,
            EntryType.AUDIO_FILE: self.delete_file_entry,
            EntryType.PDF_FILE: self.delete_file_entry,
            EntryType.GEOLOCATION: self.delete_non_file_entry,
            EntryType.ACCELEROMETER: self.delete_non_file_entry,
            EntryType.HEART_RATE: self.delete_non_file_entry,
            EntryType.SLEEP_STATE: self.delete_non_file_entry,
            EntryType.FITBIT_ACTIVITY: self.delete_non_file_entry,
        }
        # Assert that all the entry types have a deletion function
        for entry_type in EntryType:
            assert entry_type in self.deletion_map, f"Entry type {entry_type} does not have a deletion function"

        self.delete_batch = []
        self.insert_batch = []
        self.batching = False

    ###### WIP ######
    def start_batching(self):
        """
        Starts batching input entries
        """
        if self.batching:
            raise RuntimeError("Already batching")
        self.batching = True
        self.input_batch = []
        self.delete_batch = []

    def commit_batching(self):
        """
        Commits the batched entries to the database
        """
        self.rmanager.batch_delete_entries(self.delete_batch)
    ##########################

    def insert_entry(self, entry: Entry, mutate=True) -> bool:
        """
        Inserts an entry into the database

        If mutate is True, the entry will be updated if it already exists

        Returns True if the entry was mutated and False otherwise
        """
        existing_entry = self.get_entry_if_exists(entry.entry_uuid)
        if existing_entry:
            if mutate:
                # Then we are allowed to mutate, but we need to make sure to increment the mutation count
                entry.mutation_count = existing_entry.mutation_count + 1
                self.rmanager.delete_entry(entry.entry_uuid)
                self.rmanager.insert_entry(entry)
                return True
            else:
                # Then we are at an impasse since the entry already exists and we are not mutating
                raise EntryAlreadyExistsException(f"Entry with id {entry.entry_uuid} already exists")
        else:
            # Then there is no problem since the entry doesn't exist
            # and we should insert the entry without any fuss
            self.rmanager.insert_entry(entry)
            return False

    def get_entry_if_exists(self, entry_uuid: EntryUUID) -> Entry | None:
        """
        Checks if an entry already exists in the database
        """
        try:
            entry = self.rmanager.pull_entry(entry_uuid)
            return entry
        except EntryNotFoundException:
            return None

    def insert_file_entry(self, file_entry: GenericFileEntry, mutate=True, delete_old_file=True) -> bool:
        """
        Inserts a file entry into the database

        The generic file entry is expected to have a file id that points to a local file. This will be converted
        to a file id in the file store if the entry is being inserted
        """
        # Step 1: Check if the entry already exists. The entry uuid does not depend on the file id so we can check this without inserting
        existing_entry = self.get_entry_if_exists(file_entry.entry_uuid)
        # Step 2: Check if we should insert. If not, raise an exception
        if existing_entry and not mutate:
            raise EntryAlreadyExistsException(f"Entry with id {file_entry.entry_uuid} already exists")
        # Step 3: Insert the file into the file store and get the new file id while storing the old one
        file_path = file_entry.data.file_id
        new_file_id = self.rmanager.insert_file(file_path)
        # Step 4: Update the entry with the new file id
        file_entry.data.file_id = new_file_id
        # Step 5: Insert the entry into the database
        self.insert_entry(file_entry, mutate)
        # Step 6: If delete_old_file is True, delete the old file from the file store
        if delete_old_file and existing_entry:
            self.rmanager.delete_file(existing_entry.data.file_id)

        return existing_entry is not None

    def delete_group(self, group_id: str):
        """
        Deletes all entries that are part of a group
        """
        output_filter = OutputFilter(group_ids=[group_id])
        entries = self.rmanager.search_entries(output_filter)
        for entry_uuid in entries:
            self.delete_entry(entry_uuid)

    def delete_entry(self, entry_uuid: EntryUUID):
        """
        Deletes an entry from the database
        """
        entry = self.get_entry_if_exists(entry_uuid)
        if not entry:
            raise EntryNotFoundException(f"Entry with id {entry_uuid} does not exist")
        deleter = self.deletion_map[entry.entry_type]
        deleter(entry)

    def delete_non_file_entry(self, entry: Entry):
        """
        Deletes a text entry from the database
        """
        self.rmanager.delete_entry(entry.entry_uuid)

    def delete_file_entry(self, entry: GenericFileEntry):
        """
        Deletes a file entry from the database by first removing the file from the file store
        and then deleting the entry
        """
        self.rmanager.delete_file(entry.data.file_id)
        self.rmanager.delete_entry(entry.entry_uuid)

