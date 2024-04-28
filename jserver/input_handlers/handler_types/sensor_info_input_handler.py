"""
Uses the sensor info server to integrate biometrics data.

Creates its own database collection to store which source uuids have already been parsed.
"""

from pathlib import Path
import asyncio

from jserver.input_handlers.models.sensor_info import ReturnedSensorInfo, SensorInfo
from jserver.config.input_handler_config import SensorInfoHandlerConfig
from jserver.input_handlers.input_handler import InputHandler, EntryInsertionLog
from jserver.entries.types.personal_sensor_entries import HeartRateEntry, SleepStateEntry, GeolocationEntry, AccelerometerEntry
from jserver.utils.requests import get_json

from jserver.utils.logger import setup_logging
logger = setup_logging(__name__)

from typing import Callable

sensor_id_map = {
    "heart_rate": HeartRateEntry,
    "sleep": SleepStateEntry,
    "gps": GeolocationEntry,
    "accelerometer": AccelerometerEntry,
}

class SensorInfoInputHandler(InputHandler):
    _requires_db_connection = True

    def __init__(self, handler_id: str, config: SensorInfoHandlerConfig, on_entries_inserted: Callable[[list[EntryInsertionLog]], None]):
        super().__init__(handler_id, config, on_entries_inserted)

        self.sensor_info_server = config.sensor_info_server.rstrip("/")
        self.data_source_id = config.data_source_id

        self.ready = False

    def construct_endpoint(self, endpoint: str) -> str:
        """
        Constructs an endpoint for the sensor info server
        If there is a double slash in the middle, it will be replaced with a single slash
        """
        return self.sensor_info_server + "/" + endpoint.lstrip("/")

    def set_db_connection(self, db_connection):
        super().set_db_connection(db_connection)

        self.set_up_database()
        self.ready = True

    def set_up_database(self):
        self.collection = self.db_connection.get_collection("sensor_info_sources")
        self.collection.create_index("source_uuid", unique=True)

    def record_saved_source_uuid(self, source_uuid: str, timestamp: int):
        """
        Adds to the database that the source defined by the source_uuid was saved at the given timestamp
        """
        # If the source_uuid is already in the database, update the timestamp
        # If the source_uuid is not in the database, add it
        self.collection.update_one(
            {"source_uuid": source_uuid},
            {"$set": {"timestamp": timestamp}},
            upsert=True,
        )

    def get_unsaved_source_uuids(self) -> list[tuple[str, int]]:
        """
        Gets the sources from the sensor info server and check if the last updated timestamp falls
        after the last time the source was saved

        Returns a list of the source uuids that have not been saved and the last updated timestamp
        """
        endpoint = self.construct_endpoint(f"available_sensor_info?data_source_id={self.data_source_id}")
        unsaved_sources = []
        res = get_json(endpoint)
        if res is None:
            return unsaved_sources
        data: ReturnedSensorInfo = ReturnedSensorInfo.model_validate(res["data"])
        for source_uuid in data.source_uuids:
            metadata = data.metadatas[source_uuid]
            last_updated = metadata.last_updated
            if self.collection.count_documents({"source_uuid": source_uuid, "timestamp": {"$gte": last_updated}}) == 0:
                unsaved_sources.append((source_uuid, last_updated))
        return unsaved_sources

    def get_source_uuid_data(self, source_uuid: str) -> list[SensorInfo]:
        """
        Gets the data for the given source uuid
        """
        endpoint = self.construct_endpoint(f"get_sensor_info?data_source_id={self.data_source_id}&source_uuid={source_uuid}")
        res = get_json(endpoint)
        if res is None:
            return None
        data: list[SensorInfo] = res["data"]
        processed_data = []
        for info in data:
            processed_data.append(SensorInfo.model_validate(info))
        return processed_data

    async def trigger(self, entry_insertion_log: list[EntryInsertionLog] = []):
        """

        """
        unsaved_sources = self.get_unsaved_source_uuids()
        unsaved_sources = unsaved_sources[-10:]  # Only process 10 sources at a time
        if len(unsaved_sources) == 0:
            logger.info("No new sources to parse")
            return

        for source_uuid, timestamp in unsaved_sources:
            sensor_info = self.get_source_uuid_data(source_uuid)
            if sensor_info is None:
                logger.error(f"Could not get sensor info for source uuid: {source_uuid}")
                continue
            logger.info(f"Processing source uuid: {source_uuid} with {len(sensor_info)} entries")
            for index, info in enumerate(sensor_info):
                timestamp = info.timestamp
                sensor_id = info.sensor
                value = info.value
                assert sensor_id in sensor_id_map, f"Unknown sensor id: {sensor_id}"
                entry_type = sensor_id_map[sensor_id]
                location = (value["latitude"], value["longitude"]) if ("latitude" in value and "longitude" in value) else None

                # logger.info(f"Inserting entry for source uuid {source_uuid} at timestamp {timestamp} with value {value}. Location: {location}")

                entry = entry_type(
                    data=value,
                    start_time=timestamp,
                    latitude=location[0] if location is not None else None,
                    longitude=location[1] if location is not None else None,
                    group_id=f"sensor_info_{source_uuid}",
                    seq_id=index,
                    input_handler_id=self.handler_id,
                )
                self.insert_entry(entry_insertion_log, entry)
                # Give control back to the event loop
                await asyncio.sleep(0)
            logger.info(f"Finished processing source uuid: {source_uuid}")

            self.record_saved_source_uuid(source_uuid, timestamp)

    async def _on_trigger_request(self,entry_insertion_log: list[EntryInsertionLog], file: str | None = None, metadata: dict[str, str] | None = None) -> None:
        """
        """
        if not self.ready:
            logger.error("Handler is not ready")
            return

        await self.trigger()

    async def _on_trigger_new_file(self, entry_insertion_log: list[EntryInsertionLog], file: str) -> None:
        """
        """
        pass

    async def _on_trigger_interval(self, entry_insertion_log: list[EntryInsertionLog]) -> None:
        """
        """
        if not self.ready:
            logger.error("Handler is not ready")
            return

        await self.trigger()
