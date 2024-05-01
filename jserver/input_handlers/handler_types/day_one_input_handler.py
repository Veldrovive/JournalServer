from pathlib import Path
import zipfile
import json
import asyncio
import codecs
from datetime import datetime, timedelta
import pytz
import shutil
import re
import tempfile

from jserver.input_handlers.input_handler import InputHandler, EntryInsertionLog
from jserver.config.input_handler_config import DayOneHandlerConfig
from jserver.entries import TextEntry, ImageFileEntry, VideoFileEntry, AudioFileEntry, PDFileEntry, GenericFileEntry

from jserver.utils.logger import setup_logging
logger = setup_logging(__name__)

from typing import Callable, Any

file_entry_types: list[GenericFileEntry] = [ImageFileEntry, VideoFileEntry, AudioFileEntry, PDFileEntry, GenericFileEntry]
def get_file_entry_from_ext(ext: str) -> type[GenericFileEntry]:
    for file_entry_type in file_entry_types:
        if file_entry_type.is_valid_extension(ext):
            return file_entry_type
    return GenericFileEntry

def get_ms_from_date(date: str, timezone: str) -> int:
    creation_date_utc = datetime.strptime(date, '%Y-%m-%dT%H:%M:%SZ')
    creation_date_utc = pytz.utc.localize(creation_date_utc)
    timezone = pytz.timezone(timezone)
    creation_date_in_timezone = creation_date_utc.astimezone(timezone)
    milliseconds_since_epoch = int(creation_date_in_timezone.timestamp() * 1000)
    return milliseconds_since_epoch

def get_day_start_from_date(date: str, timezone: str) -> int:
    """
    Gets the milliseconds corresponding to midnight of the given date
    """
    creation_date_utc = datetime.strptime(date, '%Y-%m-%dT%H:%M:%SZ')
    creation_date_utc = pytz.utc.localize(creation_date_utc)
    timezone = pytz.timezone(timezone)
    creation_date_in_timezone = creation_date_utc.astimezone(timezone)
    creation_date_in_timezone = creation_date_in_timezone.replace(hour=0, minute=0, second=0, microsecond=0)
    milliseconds_since_epoch = int(creation_date_in_timezone.timestamp() * 1000)
    return milliseconds_since_epoch

def extract_media_info(s):
    """
    Takes a dayone file descriptor like ![](dayone-moment:/video/3C6ED0B957494BD38BC0D047D20C0CF5)
    and extracts the media type and media id
    """
    pattern = r'!\[\]\(dayone-moment:\/(\w*)?\/([A-F0-9]+)\)'

    match = re.search(pattern, s)

    if match:
        media_type = match.group(1) or "photo"
        media_id = match.group(2)
        return media_type, media_id
    return None

def string_to_timedelta_and_clean(s):
    """
    Takes a string with a timestamp at the start in the form H:MM or HH:MM and returns a timedelta object
    that represents the time and the string with the timestamp removed
    """
    # Regular expression to match the timestamp pattern at the start of the string
    pattern = r"^(\d{1,2}):(\d{2})(\s*[\r\n]?)"
    match = re.match(pattern, s)

    # Check if pattern is matched
    if match:
        # Extract hours and minutes
        hours, minutes = map(int, match.groups()[:2])

        # Create a timedelta object
        time_delta = timedelta(hours=hours, minutes=minutes)

        # Remove the matched timestamp and optional newline from the original string
        cleaned_string = re.sub(pattern, '', s, count=1)

        return time_delta, cleaned_string
    else:
        return None, s

class DayOneInputHandler(InputHandler):
    _requires_db_connection = False
    _requires_input_folder = True
    _takes_file_input = True

    def __init__(self, handler_id: str, config: DayOneHandlerConfig, on_entries_inserted: Callable[[list[EntryInsertionLog]], None]):
        super().__init__(handler_id, config, on_entries_inserted)
        self.config = config
        self.trigger_stage = "Idle"

    def get_state(self):
        return {
            "trigger_stage": self.trigger_stage
        }

    def verify_zip_file(self, file_path: Path):
        """
        Verifies that the zip file is a valid Day One zip file
        """
        if not file_path.exists():
            logger.error(f"File {file_path} does not exist")
            return False
        if not file_path.is_file():
            logger.error(f"File {file_path} is not a file")
            return False
        if file_path.suffix != ".zip":
            logger.error(f"File {file_path} is not a zip file")
            return False
        return True

    async def _on_trigger_request(self, entry_insertion_log: list[EntryInsertionLog], file: str | None = None, metadata: dict[str, str] | None = None):
        logger.info(f"Got a trigger request for day_one input handler {self.handler_id} with args {file}, {metadata}")
        # Ensure that we have a valid zip file
        if file is None:
            logger.error("No file provided for day_one input handler")
            return
        file_path = Path(file)
        if not self.verify_zip_file(file_path):
            return
        # Process the zip file
        await self.process_zip_file(entry_insertion_log, file)

    async def _on_trigger_new_file(self, entry_insertion_log: list[EntryInsertionLog], file: str):
        logger.info(f"Got a new file trigger for day_one input handler {self.handler_id} with file {file}")
        # Ensure that we have a valid zip file
        file_path = Path(file)
        if not self.verify_zip_file(file_path):
            return
        # Process the zip file
        await self.process_zip_file(entry_insertion_log, file)

    async def _on_trigger_interval(self, entry_insertion_log: list[EntryInsertionLog]):
        """
        There is no interval trigger for the Day One input handler so this method does nothing
        """
        logger.debug(f"Got an interval trigger for day_one input handler {self.handler_id}")

    async def process_zip_file(self, entry_insertion_log: list[EntryInsertionLog], file: str):
        """
        Called by trigger handlers to do the heavy lifting of processing a zip file and inserting the entries into the database
        """
        # We will extract the zip file to a temporary directory
        self.trigger_stage = "Extracting"
        asyncio.sleep(2)  # Sleep for a couple seconds to allow other processes to finish
        with tempfile.TemporaryDirectory() as temp_dir:
            dir_path = Path(temp_dir)
            # Extract the zip file
            try:
                with zipfile.ZipFile(file, 'r') as zip_ref:
                    zip_ref.extractall(dir_path)
            except zipfile.BadZipFile:
                # This usually means the zip file is in the process of being copied
                # If this happens then the code for detecting when the file is stable is not working
                logger.error(f"Bad zip file {file}")
                return

            # We now have the extracted journal files
            journal_file = dir_path / "Journal.json"
            if not journal_file.exists():
                logger.error(f"Journal file {journal_file} does not exist")
                return

            with open(journal_file, "r") as f:
                journal_data = json.load(f)

            entries = journal_data.get("entries", [])
            num_entries = len(entries)
            for i, entry in enumerate(entries):
                asyncio.sleep(0)  # Yield to other tasks
                if "text" not in entry:
                    logger.debug("Encountered empty entry")
                    continue
                self.trigger_stage = f"Removing Existing Entry {i+1}/{num_entries}"
                await self.remove_existing_journal_entry(entry)
                self.trigger_stage = f"Processing Entry {i+1}/{num_entries}"
                await self.process_journal_entry(entry_insertion_log, entry, dir_path)
            self.trigger_stage = "Idle"

    async def remove_existing_journal_entry(self, journal_entry: dict):
        """
        Removes the existing journal entry from the database if it exists
        """
        # We will use the journal entry's uuid to find the existing entries
        journal_entry_uuid = journal_entry["uuid"]
        # We will remove all entries with the same group_id
        self.emanager.delete_group(journal_entry_uuid)

    async def process_journal_entry(self, entry_insertion_log: list[EntryInsertionLog], journal_entry: dict, data_path: Path):
        """
        Processes a single Day One entry and inserts it into the database
        """
        # Create a text entry from the Day One entry
        text = journal_entry["text"]
        creation_date_str = journal_entry["creationDate"] # In the form YYY-MM-DDTHH:MM:SSZ
        creation_date_timezone = journal_entry["timeZone"] # Like America\/New_York

        lat = journal_entry["location"]["latitude"] if "location" in journal_entry else None
        lng = journal_entry["location"]["longitude"] if "location" in journal_entry else None

        journal_entry_uuid = journal_entry["uuid"]  # Used as the group_id

        # The format of the text is that paragraphs are split by double newlines
        paragraphs = text.split("\n\n")
        seq_id = 0

        # We will keep the last paragraph's date so that if an un-timestamped paragraph follows, we can use the last paragraph's date
        current_time = get_ms_from_date(creation_date_str, creation_date_timezone)  # Start with the entry's creation date
        # We handle the case where a file has a timestamp outside of the entry's creation date separately
        # If it does fall outside the entry's day, we treat it as if it were no timestamped so it just flows with the current time
        day_start = get_day_start_from_date(creation_date_str, creation_date_timezone)
        day_end = day_start + 24 * 60 * 60 * 1000 - 1 # The end of the day is 23:59:59.999

        # Some paragraphs (like a link) are duplicated in sequence. We de-duplicate by only inserting
        # the first instance of a paragraph
        last_uuid = None

        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            is_file = paragraph.startswith("![")
            if is_file:
                entry = self.handle_file_entry(
                    paragraph,
                    data_path=data_path,
                    journal_entry=journal_entry,
                    current_time=current_time,
                    time_bounds=(day_start, day_end),
                    entry_location=(lat, lng),
                    group_params=(journal_entry_uuid, seq_id)
                )
                if entry is None:
                    # There was an error processing the file entry
                    continue
                # DayOne duplicates some entries. We only take one.
                if entry.entry_uuid != last_uuid:
                    self.insert_file_entry(entry_insertion_log, entry)
                    seq_id += 1
                    last_uuid = entry.entry_uuid
            else:
                entry = self.handle_text_entry(
                    paragraph,
                    journal_entry=journal_entry,
                    current_time=current_time,
                    time_bounds=(day_start, day_end),
                    entry_location=(lat, lng),
                    group_params=(journal_entry_uuid, seq_id)
                )
                # DayOne duplicates some entries. We only take one.
                if entry.entry_uuid != last_uuid:
                    self.insert_entry(entry_insertion_log, entry)
                    seq_id += 1
                    last_uuid = entry.entry_uuid
            # We also want to update the current timestamp with the new entry's timestamp
            # As long as it fits within the bounds of the day we will take it (even if that means going back in time)
            clamp = lambda x, low, high: max(low, min(x, high))
            entry_end_time = entry.end_time if entry.end_time is not None else entry.start_time
            current_time = clamp(entry_end_time, day_start, day_end)

    def handle_file_entry(
        self,
        paragraph: str,
        data_path: Path,
        journal_entry: dict[str, Any],
        current_time: int,
        time_bounds: tuple[int, int],
        entry_location: tuple[float, float],
        group_params: tuple[str, int]
    ) -> GenericFileEntry:
        """
        Constructs a file entry (with the file_id being the path to the file) from the paragraph

        A file entry is a paragraph that starts with ![ and ends with )
        Examples:
            Image: ![](dayone-moment://33253761E2374C11AEF822C74E39CF7C) - (We call this media type "photo")
            Video: ![](dayone-moment:/video/3C6ED0B957494BD38BC0D047D20C0CF5)
            Audio: ![](dayone-moment:/audio/2A40FA830E7C402A86D6C9274D8BA044)
            PDF:   ![](dayone-moment:/pdfAttachment/05F621DB7F2A4A69A7CB361022AD42EF)
        """
        media_type, media_id = extract_media_info(paragraph)  # ![](dayone-moment:/{media_type}/{media_id})
        # The folder where the actual file is stored depends on the media type. We map the media type to the folder name
        folder_name_map = {
            "photo": "photos",
            "video": "videos",
            "audio": "audios",
            "pdfAttachment": "pdfs",
        }
        try:
            folder_name = folder_name_map[media_type]
        except KeyError:
            logger.error(f"Unsupported media type {media_type}")
            return None
        media_folder_path = data_path / folder_name

        # We also need to get more information about the media file from the journal entry
        journal_media_metadata_dict_list = journal_entry[f"{media_type}s"]
        # We can search the list of media metadata dictionaries for the one that matches the media_id
        journal_media_metadata_dict = None
        for journal_media_metadata in journal_media_metadata_dict_list:
            if journal_media_metadata["identifier"] == media_id:
                journal_media_metadata_dict = journal_media_metadata
                break
        else:
            # Then we could not find the media metadata for the media id and we cannot proceed
            logger.error(f"Could not find media metadata for media id {media_id}")
            return None

        # If the file has a timestamp we can update the current time
        media_timestamp = current_time
        if "date" in journal_media_metadata_dict:
            media_date = journal_media_metadata_dict["date"]  # In the form YYY-MM-DDTHH:MM:SSZ
            creation_date_timezone = journal_entry["timeZone"]  # Like America\/New_York
            new_media_timestamp = get_ms_from_date(media_date, creation_date_timezone)
            if time_bounds[0] <= new_media_timestamp <= time_bounds[1]:
                # The timestamp is within the bounds of the day so we use it
                media_timestamp = new_media_timestamp
            else:
                logger.warning(f"Media timestamp {media_date} is outside of the bounds of the day {time_bounds} - {media_id}")

        # Likewise, if the media has a location we can update the entry location
        media_location = entry_location
        if "location" in journal_media_metadata_dict:
            location_data = journal_media_metadata_dict["location"]
            if "region" in location_data:
                lat = journal_media_metadata_dict["location"]["region"]["center"]["latitude"]
                lng = journal_media_metadata_dict["location"]["region"]["center"]["longitude"]
                media_location = (lat, lng)
            elif "latitude" in location_data:
                lat = journal_media_metadata_dict["location"]["latitude"]
                lng = journal_media_metadata_dict["location"]["longitude"]
                media_location = (lat, lng)

        # TODO: For videos, get the end time

        # More weird DayOne stuff. The filename begins with the md5 hash, but in some cases we don't know the extension
        # In those cases we just search the media to find the one that begins with the md5 hash
        md5_hash = journal_media_metadata_dict['md5']
        try:
            file_type = journal_media_metadata_dict['type']
            media_file_name = f"{md5_hash}.{file_type}"
            media_file_path = media_folder_path / media_file_name
            if not media_file_path.exists():
                raise RuntimeError(f"Could not find media file: {media_file_path}")
        except (KeyError, RuntimeError):
            # Then we will try to use a fallback method to find the file of iterating over everything
            # in the media folder path and finding the file that starts with the md5
            for file in media_folder_path.iterdir():
                if file.name.startswith(journal_media_metadata_dict["md5"]):
                    media_file_path = file
                    break
            else:
                raise RuntimeError(f"Could not find media file: {media_file_path}")

        # Now we have all the required information to create the file entry
        file_entry_type = get_file_entry_from_ext(media_file_path.suffix)

        file_detail = file_entry_type.generate_file_detail(
            media_file_path,
            journal_media_metadata_dict
        )

        entry = file_entry_type(
            data=file_detail,
            start_time=media_timestamp,
            end_time=None,  # TODO: Get the end time for videos
            latitude=media_location[0],
            longitude=media_location[1],
            group_id=group_params[0],
            seq_id=group_params[1],
            input_handler_id=self.handler_id,
            tags=[],
        )
        return entry

    def handle_text_entry(
        self,
        paragraph: str,
        journal_entry: dict[str, Any],
        current_time: int,
        time_bounds: tuple[int, int],
        entry_location: tuple[float, float],
        group_params: tuple[str, int]
    ) -> TextEntry:
        """
        Constructs a text entry from the paragraph

        If the paragraph begins with a timestamp (HH:MM) then we use that as the timestamp for the entry
        """
        p_time, paragraph = string_to_timedelta_and_clean(paragraph)

        # If the paragraph began with a timestamp p_time is a timedelta object
        entry_timestamp = current_time
        if p_time is not None:
            time_offset_ms = int(round(p_time.total_seconds() * 1000))
            day_start_time = time_bounds[0]
            entry_timestamp = day_start_time + time_offset_ms

        # Not sure exactly what is going on with the \\s, but they don't correspond to anything we want to see
        paragraph = paragraph.replace("\\", "")

        entry = TextEntry(
            data=paragraph,
            start_time=entry_timestamp,
            latitude=entry_location[0],
            longitude=entry_location[1],
            group_id=group_params[0],
            seq_id=group_params[1],
            input_handler_id=self.handler_id,
            tags=[],
        )
        return entry
