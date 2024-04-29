from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

from jserver.storage.db import DatabaseManager
from jserver.config import Config, MongoDatabaseManagerConfig
from jserver.entries import Entry, validate_entry
from jserver.storage.primitives import OutputFilter
from jserver.exceptions import *

from jserver.utils.logger import setup_logging
logger = setup_logging(__name__)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from jserver.entries.primitives import EntryUUID

class MongoDatabaseManager(DatabaseManager):
    def __init__(self, config: 'Config'):
        self.database_config = config.storage_manager.database_manager
        if not isinstance(self.database_config, MongoDatabaseManagerConfig):
            raise ValueError("Invalid database manager config. Expected MongoDatabaseManagerConfig")
        host = self.database_config.host
        port = self.database_config.port
        username = self.database_config.username
        password = self.database_config.password
        database_name = self.database_config.database

        self.client = MongoClient(host, port, username=username, password=password)
        self.database = self.client[database_name]
        self.create_indexes()

    def create_indexes(self):
        """
        Create indexes for frequently queried fields for efficiency.
        """
        # Index for entries collection
        self.database.entries.create_index("entry_uuid", unique=True)
        # And on the entry type
        self.database.entries.create_index("entry_type")
        # And on the timestamp so that we can query by time
        self.database.entries.create_index("start_time")
        # And by group id so that we load all entries for a group
        self.database.entries.create_index("group_id")
        # And by latitude and longitude so that we can query by location
        self.database.entries.create_index([("latitude", 1), ("longitude", 1)])

    def get_database_connection(self, db_name: str):
        return self.client[db_name]

    def insert_entry(self, entry: Entry) -> None:
        """
        Entries are defined such that they are fully serializable by pydantic.
        """
        entry_dict = entry.model_dump()
        try:
            self.database.entries.insert_one(entry_dict)
        except DuplicateKeyError as e:
            raise EntryAlreadyExistsException(f"Entry with id {entry.entry_uuid} already exists")

    def delete_entry(self, entry_id: 'EntryUUID') -> None:
        self.database.entries.delete_one({"entry_uuid": entry_id})

    def pull_entry(self, entry_id: 'EntryUUID') -> Entry:
        entry_dict = self.database.entries.find_one({"entry_uuid": entry_id})
        if entry_dict is None:
            raise EntryNotFoundException(f"Entry with id {entry_id} not found")
        entry = validate_entry(entry_dict)
        return entry

    def pull_entries(self, entry_ids: list['EntryUUID']) -> list[Entry]:
        entries = self.database.entries.find({"entry_uuid": {"$in": entry_ids}})
        results_map = { entry["entry_uuid"]: entry for entry in entries }
        try:
            return [validate_entry(results_map[entry_id]) for entry_id in entry_ids]
        except KeyError as e:
            raise EntryNotFoundException(f"Entry with id {e} not found")

    def search_entries(self, filter: OutputFilter) -> list['EntryUUID']:
        """
        Returns a list of entry uuids that match the given filter
        """
        logger.info(f"Searching for entries with filter: {filter}")
        query = {}
        # Filtering by start time
        if filter.timestamp_after is not None:
            query["start_time"] = { "$gte": filter.timestamp_after }
        if filter.timestamp_before is not None:
            if "start_time" in query:
                query["start_time"]["$lte"] = filter.timestamp_before
            else:
                query["start_time"] = { "$lte": filter.timestamp_before }

        # Filtering by location
        if filter.location is not None:
            center = filter.location.center
            radius = filter.location.radius
            # We are going to use a square filter for now
            query["latitude"] = {"$gte": center[0] - radius, "$lte": center[0] + radius}
            query["longitude"] = {"$gte": center[1] - radius, "$lte": center[1] + radius}

        # Filtering by entry type
        if filter.entry_types is not None:
            if len(filter.entry_types) == 1:
                query["entry_type"] = filter.entry_types[0]
            else:
                query["entry_type"] = {"$in": filter.entry_types}

        # Filtering by input handler id
        if filter.input_handler_ids is not None:
            if len(filter.input_handler_ids) == 1:
                query["input_handler_id"] = filter.input_handler_ids[0]
            else:
                query["input_handler_id"] = {"$in": filter.input_handler_ids}

        # Filtering by group id
        if filter.group_ids is not None:
            if len(filter.group_ids) == 1:
                query["group_id"] = filter.group_ids[0]
            else:
                query["group_id"] = {"$in": filter.group_ids}

        # Execute the query
        logger.info(f"Mongo Entry Database Query: {query}")
        entries = self.database.entries.find(query)
        entry_uuids = [entry["entry_uuid"] for entry in entries]
        logger.info(f"Found {len(entry_uuids)} entries")

        return entry_uuids
