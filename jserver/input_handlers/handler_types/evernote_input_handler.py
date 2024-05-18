from evernote.api.client import EvernoteClient
from evernote.edam.notestore import NoteStore
from lxml import etree
from markdownify import markdownify as md
import requests
import re
import tempfile
import datetime

from jserver.config.input_handler_config import EvernoteAPIHandlerConfig
from jserver.input_handlers.input_handler import InputHandler, EntryInsertionLog
from jserver.entries import Entry, TextEntry, GenericFileEntry, ImageFileEntry, VideoFileEntry, AudioFileEntry, PDFileEntry
from jserver.utils.notion import parse_date_block
from jserver.utils.file_metadata import extract_file_metadata

from jserver.utils.logger import setup_logging
logger = setup_logging(__name__)

from typing import Callable

# from pathlib import Path
# note_persist_path = Path(__file__).parent / 'note_persist'
# note_persist_path.mkdir(exist_ok=True)

class EvernoteAuth:
    """

    """
    def __init__(self, key_collection, consumer_key, consumer_secret):
        self.key_collection = key_collection
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret

        self.authorized = False
        self.profile = None
        self.user_info = None

        self.oauth_token = None
        self.oauth_token_secret = None

        logger.info(f"Creating EvernoteAuth with consumer_key: {consumer_key}, consumer_secret: {consumer_secret}")
        self.auth_client = EvernoteClient(
            consumer_key=self.consumer_key,
            consumer_secret=self.consumer_secret,
            sandbox=False
        )
        self.access_client = None

        access_token = self.get_access_token()
        if access_token is not None:
            logger.info(f"Found access token in database, setting up client")
            self.set_access_token(access_token)  # Creates an authorized client

    def save_access_token(self, access_token):
        self.key_collection.delete_many({})
        self.key_collection.insert_one({'access_token': access_token})

    def get_access_token(self):
        access_token = self.key_collection.find_one()
        if access_token is None:
            return None
        return access_token['access_token']

    def get_authorization_url(self, callback_url):
        """
        Generate a URL that the user can visit to authorize the application
        It will redirect to the callback URL with the oauth_verifier
        """
        logger.info(f"Getting authorization URL with callback_url: {callback_url}")
        request_token_res = self.auth_client.get_request_token(callback_url)

        if not ('oauth_callback_confirmed' in request_token_res and request_token_res['oauth_callback_confirmed'] == 'true'):
            return None

        self.oauth_token = request_token_res['oauth_token']
        self.oauth_token_secret = request_token_res['oauth_token_secret']

        authorize_url = self.auth_client.get_authorize_url(request_token_res)
        return authorize_url

    def set_auth_verifier(self, auth_verifier):
        """
        Uses an auth verifier that the frontend sends to get an access token
        """
        access_token = self.auth_client.get_access_token(self.oauth_token, self.oauth_token_secret, auth_verifier)
        return self.set_access_token(access_token)

    def set_access_token(self, access_token):
        """
        Uses an auth code to generate an authorized client
        """
        self.access_token = access_token
        self.save_access_token(access_token)
        self.access_client = EvernoteClient(token=access_token, sandbox=False)

        self.note_store = self.access_client.get_note_store()
        self.user_store = self.access_client.get_user_store()

        return self.check_authorization()

    def check_authorization(self):
        """
        Makes a test request to see if the client is authorized
        """
        raw_profile = None
        try:
            raw_profile = self.user_store.getUser()
            raw_user_info = self.user_store.getPublicUserInfo(raw_profile.username)
            self.profile = {
                "id": raw_profile.id,
                "username": raw_profile.username,
                "name": raw_profile.name,
            }
            self.user_info = raw_user_info
            self.authorized = True
            logger.info(f"Successfully authorized user: {self.profile}")
            return True
        except Exception as e:
            self.profile = None
            self.authorized = False
            logger.error(f"Failed to authorize user: {e}")
            logger.info(f"Raw profile: {raw_profile}")
            return False

class EvernoteAPI:
    def __init__(self, authenticator: EvernoteAuth):
        self.authenticator = authenticator

    def get_sync_state(self):
        return self.authenticator.note_store.getSyncState()

    def get_user(self):
        return self.authenticator.user_store.getUser()

    def get_notebooks(self):
        """
        Returns a list of notebook objects
        https://dev.evernote.com/doc/reference/Types.html#Struct_Notebook
        """
        return self.authenticator.note_store.listNotebooks()

    def get_notes(self, notebook_guid, min_last_updated=0):
        """
        Returns a list of note objects inside a notebook
        https://dev.evernote.com/doc/reference/NoteStore.html#Fn_NoteStore_findNotesMetadata
        https://dev.evernote.com/doc/articles/searching_notes.php
        https://dev.evernote.com/doc/articles/search.php
        """
        filter = NoteStore.NoteFilter()
        filter.notebookGuid = notebook_guid
        filter.ascending = False  # Sort by most recent

        spec = NoteStore.NotesMetadataResultSpec()
        spec.includeTitle = True  # Get the title
        spec.includeUpdated = True  # Get the last updated time
        spec.includeUpdateSequenceNum = True  # Get the update sequence number

        curr_offset = 0
        max_notes = 100  # Max number of notes to get
        notes = []
        # Iterate until we get all the notes or a note update time is less than min_last_updated
        while True:
            note_list = self.authenticator.note_store.findNotesMetadata(filter, curr_offset, max_notes, spec)
            for note in note_list.notes:
                if note.updated < min_last_updated:
                    return notes
                notes.append(note)
            curr_offset += len(note_list.notes)
            num_remaining = note_list.totalNotes - curr_offset
            if num_remaining <= 0:
                break
            if num_remaining < max_notes:
                max_notes = num_remaining

        return notes

    def get_resource_link(self, resource_guid: str):
        """
        Returns a link to the resource
        """
        return f"{self.authenticator.user_info.webApiUrlPrefix}/res/{resource_guid}"

    def get_resource_attributes(self, resource_guid: str):
        """
        https://dev.evernote.com/doc/reference/NoteStore.html#Fn_NoteStore_getResourceAttributes
        """
        return self.authenticator.note_store.getResourceAttributes(resource_guid)


    def download_resource(self, resource_guid: str, file_path: Path):
        """
        Downloads a resource to the specified path. In order to download a resource the following request format is needed:
        ```
        POST [apiPrefix]/res/[resource_guid] HTTP/1.1
        Host: www.evernote.com
        Content-Length: 99
        Content-Type: application/x-www-form-urlencoded
        auth=[ACCESS_TOKEN]
        ```
        The token is passed in a URL-encoded POST parameter named auth

        We stream the response content to the file_path
        """
        resource_url = self.get_resource_link(resource_guid)
        access_token = self.authenticator.access_token
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "auth": access_token
        }
        with requests.get(resource_url, headers=headers, stream=True) as r:
            r.raise_for_status()
            with file_path.open('wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

    def get_note(self, note_id, with_content=True, with_resource_data=False, with_resources_recognition=False, with_resources_alternate_data=False):
        """
        Returns a note object
        https://dev.evernote.com/doc/reference/NoteStore.html#Fn_NoteStore_getNote
        """
        return self.authenticator.note_store.getNote(note_id, with_content, with_resource_data, with_resources_recognition, with_resources_alternate_data)

    # def get_note(self, note_id):
    #     """
    #     Returns a note object
    #     https://dev.evernote.com/doc/reference/NoteStore.html#Fn_NoteStore_getNoteWithResultSpec
    #     """
    #     notes_spec = NoteStore.NoteResultSpec()
    #     notes_spec.includeContent = True
    #     notes_spec.includeNoteAppDataValues = True
    #     notes_spec.includeResourceAppDataValues = True

class EvernoteInputHandler(InputHandler):
    _requires_db_connection = True
    _takes_file_input = False
    _requires_input_folder = False

    def __init__(self, handler_id: str, config: EvernoteAPIHandlerConfig, on_entries_inserted: Callable[[list[EntryInsertionLog]], None], db_connection):
        super().__init__(handler_id, config, on_entries_inserted, db_connection)

        self.ready = False
        self.set_up_database()

        self.authenticator = EvernoteAuth(self.auth_keys_collection, config.consumer_key, config.consumer_secret)
        self.api = EvernoteAPI(self.authenticator)

    def set_up_database(self):
        """
        Constructs three collections
        1. auth_keys - stores the access token
        2. notebooks - stores processed page ids and the last update time when processing
        3. blocks - stores processed block ids, the page id they belong to, the last update time when processing, and a data hash to check for updates
        4. Sync State - Stores the sync state int of the user (used to check if an update to the user's notes has occurred)
        """
        self.auth_keys_collection = self.db_connection.get_collection('auth_keys')
        self.notebooks_collection = self.db_connection.get_collection('notebooks')
        self.notes_collection = self.db_connection.get_collection('notes')
        self.sync_state_collection = self.db_connection.get_collection('sync_state')

        self.notebooks_collection.create_index('id', unique=True)
        self.notes_collection.create_index('id', unique=True)
        self.notes_collection.create_index('notebook_id')

    ######## DATABASE METHODS ########
    def set_sync_state(self, sync_count: int):
        self.sync_state_collection.delete_many({})
        self.sync_state_collection.insert_one({'sync_count': sync_count})

    def get_sync_state(self):
        sync_state = self.sync_state_collection.find_one()
        if sync_state is None:
            return -1
        return sync_state['sync_count']

    def get_notebook_update_data(self, notebook_id: str):
        notebook = self.notebooks_collection.find_one({'id': notebook_id})
        if notebook is None:
            return None, None
        return notebook['last_update'], notebook['seq_num']

    def set_notebook_update_data(self, notebook_id: str, last_update: int, seq_num: int):
        self.notebooks_collection.update_one({'id': notebook_id}, {'$set': {'last_update': last_update, 'seq_num': seq_num}}, upsert=True)

    def get_note_update_data(self, note_id: str):
        note = self.notes_collection.find_one({'id': note_id})
        if note is None:
            return None, None
        return note['last_update'], note['seq_num']

    def set_note_update_data(self, note_id: str, notebook_id: str, last_update: int, seq_num: int):
        self.notes_collection.update_one({'id': note_id}, {'$set': {'last_update': last_update, 'notebook_id': notebook_id, 'seq_num': seq_num}}, upsert=True)
    ######## END DATABASE METHODS ########

    ######## RPC METHODS ########
    def get_authorization_url(self, req: dict):
        return {
            "url": self.authenticator.get_authorization_url(**req)
        }

    def set_auth_verifier(self, req: dict):
        success = self.authenticator.set_auth_verifier(**req)
        if success:
            return {
                "success": True,
                "profile": self.authenticator.profile,
            }
        else:
            self.profile = None
            return {
                "success": False,
                "profile": None,
            }

    @property
    def _rpc_map(self):
        return {
            'get_authorization_url': self.get_authorization_url,
            'set_auth_verifier': self.set_auth_verifier
        }
    ######## END RPC METHODS ########

    def get_state(self):
        """
        Gets the state of the input handler
        """
        return {
            "authorized": self.authenticator.authorized,
            "profile": self.authenticator.profile,
        }

    def get_updated_notebooks(self):
        """
        Returns a list of notebook guids that have a serviceUpdated time greater than that stored in the database
        """
        notebooks = self.api.get_notebooks()
        updated_notebooks = []
        for notebook in notebooks:
            guid = notebook.guid
            name = notebook.name
            last_updated = notebook.serviceUpdated
            seq_num = notebook.updateSequenceNum  # Changes whenever the notebook is updated

            logger.info(f"Notebook: {name}, {guid}, {last_updated}")

            prev_last_updated, prev_seq_num = self.get_notebook_update_data(guid)
            timestamp_updated = prev_last_updated is None or prev_last_updated < last_updated
            seq_num_updated = prev_seq_num is None or prev_seq_num < seq_num
            if timestamp_updated or seq_num_updated:
                logger.info(f"Notebook {name} has been updated\n")
                updated_notebooks.append((guid, name, last_updated, seq_num))
            else:
                logger.info(f"Notebook {name} has not been updated\n")

        return updated_notebooks

    def get_updated_notes(self, notebook_guid: str, notebook_update_time: int):
        """
        Returns a list of note guids that have a serviceUpdated time greater than that stored in the database
        """
        notes = self.api.get_notes(notebook_guid, notebook_update_time - 1)
        updated_notes = []
        for note in notes:
            guid = note.guid
            title = note.title
            last_updated = note.updated
            seq_num = note.updateSequenceNum  # Changes whenever the note is updated

            logger.info(f"Note: {title}, {guid}, {last_updated}")

            prev_last_updated, prev_seq_num = self.get_note_update_data(guid)
            timestamp_updated = prev_last_updated is None or prev_last_updated < last_updated
            seq_num_updated = prev_seq_num is None or prev_seq_num < seq_num
            if timestamp_updated or seq_num_updated:
                logger.info(f"Note {title} has been updated\n")
                updated_notes.append((guid, title, last_updated, seq_num))
            else:
                logger.info(f"Note {title} has not been updated\n")

        return updated_notes

    def get_day_bounds(self, created_time: int, title: str):
        """
        If the title is of the form "[MONTH] [DAY], [YEAR]", then we use that as the day
        Otherwise we get the day bounds based on the created time and the device's timezone
        """
        tzinfo = datetime.datetime.now().astimezone().tzinfo
        match = re.match(r"(\w+) +(\d+),? +(\d+)", title)
        if match is not None:
            month, day, year = match.groups()
            day = int(day)
            year = int(year)
            if year < 1000:  # You probably aren't inventing algebra right now
                year += 2000
            month = datetime.datetime.strptime(month, "%B").month
            created_time_dt = datetime.datetime(year, month, day, tzinfo=tzinfo)
            start_time = created_time_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = created_time_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
        else:
            created_time_dt = datetime.datetime.fromtimestamp(created_time / 1000, tz=tzinfo)
            start_time = created_time_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = created_time_dt.replace(hour=23, minute=59, second=59, microsecond=999999)

        return int(start_time.timestamp() * 1000), int(end_time.timestamp() * 1000)

    def process_note_content(self, note_content: str, resources: list[dict]):
        """

        """
        parser = etree.XMLParser(remove_blank_text=True)
        root = etree.fromstring(note_content, parser)

        for resource in resources:
            resource_id = resource.guid
            resource_data = self.api.get_resource_attributes(resource_id)
            logger.info(f"Resource: {resource_id}, {resource_data}")

        content = []
        resource_number = 0

        for child in root:
            if child.tag == 'div':
                # Check if the div contains only a <br/>
                if len(child) == 1 and child[0].tag == 'br':
                    new_content = None
                else:
                    new_content = {
                        "type": "text",
                        "text": md(etree.tostring(child, method='html', encoding='unicode'))
                    }
            elif re.match(r'h[1-6]', child.tag):
                new_content = {
                    "type": "text",
                    "text": md(etree.tostring(child, method='html', encoding='unicode'))
                }
            elif child.tag == 'en-media':
                resource = resources[resource_number]
                resource_number += 1
                new_content = {
                    "type": "resource",
                    "guid": resource.guid,
                    "mime": resource.mime,
                    "timestamp": resource.attributes.timestamp if resource.attributes.timestamp is not None else None,
                    "latitude": resource.attributes.latitude if resource.attributes.latitude is not None else None,
                    "longitude": resource.attributes.longitude if resource.attributes.longitude is not None else None,
                    "fileName": resource.attributes.fileName if resource.attributes.fileName is not None else None,
                }
            else:
                logger.warning(f"Unknown tag: {child.tag}")
                new_content = None

            if new_content is not None and new_content["type"] == "text":
                # Then we also want to check if this was actually a timestamp
                if time_offset := parse_date_block(new_content["text"]):
                    new_content["type"] = "timestamp"
                    new_content["timestamp"] = time_offset

            # We skip over all blank blocks if the content is empty
            if len(content) == 0 and new_content is None:
                continue

            content.append(new_content)

        return content

    def process_note(self, note_id: str, resource_path: Path) -> tuple[list[Entry], list[str]]:
        """
        Returns a tuple of new entry objects and a list of entry ids that were removed
        """
        note = self.api.get_note(note_id)

        group_id = note.guid  # Every entry derived from this note has a group id of the note guid
        title = note.title
        created_time = note.created
        raw_content = note.content
        resources = note.resources

        day_start_time, day_end_time = self.get_day_bounds(created_time, title)
        logger.info(f"\n***** Processing note to content list *****")
        content = self.process_note_content(raw_content, resources)
        logger.info(f"\n***** Finished processing note *****n\n")

        logger.info(f"\n***** Searching for entries in the database from the same note *****")
        # Search the entries database for entries with the same group id
        prev_entry_ids = self.emanager.get_group_entry_ids(group_id)
        # These will eventually be used to remove entries that no longer exist in the note
        logger.info(f"\n***** Finished searching for entries in the database from the same note *****\n\n")

        if len(content) == 0:
            return [], prev_entry_ids  # The note is now blank, so we remove all entries

        # Our next job is to process the content into timestamped chunks
        # Adjacent text blocks are combined into a single block with a \n separator
        monotonic_curr_time = day_start_time
        if day_start_time <= created_time <= day_end_time:
            # Then we can start the day with the note so the first text entry will be at the same time as the note was created
            monotonic_curr_time = created_time
        if content[0]["type"] == "timestamp":
            # In order of precedence, if the first block is a timestamp, we use that offset from the day start time
            # before we use the note creation time
            monotonic_curr_time = day_start_time + content[0]["timestamp"]

        entries = []

        current_time = monotonic_curr_time
        entry_count = 0
        curr_text = ""
        curr_resource = None
        prev_content_type = None  # "text", "resource", or None
        logger.info(f"\n***** Processing content blocks to entries *****")
        for block in content + [None]:  # Append none so that the last block is processed
            """
            Any new time source such as a timestamp block or a file with a creation time will update the current time (unless it is out of bounds)
            If the current time > monotonic_curr_time, then monotonic_curr_time = current_time
            When we hit a blank block, we reset the current time = monotonic_curr_time
            """
            block_type = block["type"] if block is not None else None

            # First, we need to decide if the previous blocks should be processed into an entry
            # If we are at a timestamp or a null block, we process the previous blocks
            # If the content type changes, we process the previous blocks
            # If the content type is a resource, we process the previous blocks
            # However, we only update the timestamp if the block is a timestamp or None
            if block_type in ["timestamp", None] or block_type != prev_content_type or block_type == "resource":
                if prev_content_type is not None:
                    logger.info(f"\n~~~~~~~~~~~~~~")
                    # Create the entry and reset curr_text, curr_resource,
                    # and set prev_content_type to the new block type
                    entry_constructor = None
                    data = None
                    start_time = current_time
                    end_time = None
                    latitude = None
                    longitude = None
                    group_id = note.guid
                    seq_id = entry_count
                    input_handler_id = self.handler_id
                    if prev_content_type == "text":
                        entry_constructor = TextEntry
                        data = curr_text
                    elif prev_content_type == "resource":
                        if curr_resource["duration"] is not None:
                            end_time = start_time + curr_resource["duration"]
                        if curr_resource["location_data"] is not None:
                            latitude, longitude = curr_resource["location_data"]

                        mime = curr_resource["mime"]
                        if mime.startswith("image"):
                            entry_constructor = ImageFileEntry
                            data = ImageFileEntry.generate_file_detail(
                                file_path = curr_resource["path"],
                                file_metadata = {},
                                use_path_as_id = True
                            )
                        elif mime.startswith("video"):
                            entry_constructor = VideoFileEntry
                            data = VideoFileEntry.generate_file_detail(
                                file_path = curr_resource["path"],
                                file_metadata = {},
                                use_path_as_id = True
                            )
                        elif mime.startswith("audio"):
                            entry_constructor = AudioFileEntry
                            data = AudioFileEntry.generate_file_detail(
                                file_path = curr_resource["path"],
                                file_metadata = {},
                                use_path_as_id = True
                            )
                        elif mime.startswith("application/pdf"):
                            entry_constructor = PDFileEntry
                            data = PDFileEntry.generate_file_detail(
                                file_path = curr_resource["path"],
                                file_metadata = {},
                                use_path_as_id = True
                            )
                        else:
                            entry_constructor = GenericFileEntry
                            data = GenericFileEntry.generate_file_detail(
                                file_path = curr_resource["path"],
                                file_metadata = {},
                                use_path_as_id = True
                            )
                    assert entry_constructor is not None, f"Entry constructor is None for block type: {prev_content_type}"

                    # Construct the entry
                    entry_data = {
                        "data": data,
                        "start_time": start_time,
                        "end_time": end_time,
                        "latitude": latitude,
                        "longitude": longitude,
                        "group_id": group_id,
                        "seq_id": seq_id,
                        "input_handler_id": input_handler_id
                    }
                    logger.info(f"Creating new entry: {entry_data}\nResetting accumulators\n\n-----------\n\n")
                    entry = entry_constructor(**entry_data)
                    entries.append(entry)

                    # Reset the variables
                    entry_count += 1
                    curr_text = ""
                    curr_resource = None
                    prev_content_type = None

            logger.info(f"Processing block: {block}")
            if block_type == "timestamp":
                assert curr_resource is None, "Current resource is not None"
                assert curr_text == "", "Current text is not empty"
                new_time = day_start_time + block["timestamp"]
                if new_time > day_end_time:
                    new_time = day_end_time
                current_time = new_time
                logger.info(f"Encountered timestamp block. Setting current time to {current_time - day_start_time} ms from day start\n")
            elif block_type is None:
                assert curr_resource is None, "Current resource is not None"
                assert curr_text == "", "Current text is not empty"
                current_time = monotonic_curr_time
                logger.info(f"Encountered blank block. Resetting current time to monotonic time: {current_time - day_start_time} ms from day start\n")
            elif block_type == "text":
                # Now we are ready to process the block
                assert curr_resource is None, "Current resource is not None"
                if len(curr_text) > 0:
                    curr_text += "\n\n"
                curr_text += block["text"]
                prev_content_type = "text"
                logger.info(f"Encountered text block. Appended text is now {curr_text}\n")
            elif block_type == "resource":
                # First, we download the resource into the resource path
                assert curr_resource is None, "Current resource is not None"
                assert curr_text == "", "Current text is not empty"
                resource = block["guid"]
                resource_mime = block["mime"]

                resource_folder = resource_path / f"{resource}"
                resource_folder.mkdir(exist_ok=True)

                if block["fileName"] is not None:
                    resource_file = resource_folder / block["fileName"]
                else:
                    resource_file = resource_folder / f"{resource}.{resource_mime.split('/')[1]}"

                creation_time_ms = block["timestamp"]
                location_data = (block["latitude"], block["longitude"]) if block["latitude"] is not None and block["longitude"] is not None else None

                self.api.download_resource(resource, resource_file)

                # Extract metadata from the resource
                meta_timestamp, meta_location, duration = extract_file_metadata(resource_file)
                logger.info(f"Resource metadata: {meta_timestamp}, {meta_location}, {duration}")

                if creation_time_ms is not None and day_start_time <= creation_time_ms <= day_end_time:
                    # Then the current time takes the creation time
                    current_time = creation_time_ms

                curr_resource = {
                    "path": resource_file,
                    "mime": resource_mime,
                    "creation_time": creation_time_ms,
                    "location_data": location_data,
                    "duration": duration
                }
                prev_content_type = "resource"

                logger.info(f"Encountered resource block. Current resource is now {curr_resource}\n")

            if current_time > monotonic_curr_time:
                logger.info(f"Current time is greater than monotonic time. Updating monotonic time to {current_time - day_start_time} ms from day start")
                monotonic_curr_time = current_time

        logger.info(f"\n***** Finished processing content blocks to entries *****\n\n")

        # Find which entries in the prev_entry_ids list are not in the new entry list
        new_entry_ids = [entry.entry_uuid for entry in entries]
        removed_entry_ids = set(prev_entry_ids) - set(new_entry_ids)

        logger.info(f"Removed entry ids: {removed_entry_ids} ({len(removed_entry_ids)} entries)")

        return entries, list(removed_entry_ids)


        # note_path = note_persist_path / title
        # note_path.mkdir(exist_ok=True)

        # resource_path = note_path / 'resources'
        # resource_path.mkdir(exist_ok=True)

        # # Save the raw note to a file
        # note_file = note_path / f"{note_id}.enote"
        # with note_file.open('w') as f:
        #     f.write(content)

        # # Process the content

        # # Save the processed content to a file
        # import json
        # content_file = note_path / f"{note_id}.content"
        # with content_file.open('w') as f:
        #     f.write(json.dumps(content, indent=2))

        # resources = []
        # for resource in note.resources:
        #     resources.append({
        #         "guid": resource.guid,
        #         "mime": resource.mime,
        #         "data": resource.data.body
        #     })
        # # Save the resources to a file
        # resources_file = note_path / f"{note_id}.resources"
        # with resources_file.open('w') as f:
        #     f.write(json.dumps(resources))

        # # Download all the resources
        # for resource in note.resources:
        #     resource_file = resource_path / f"{resource.guid}.{resource.mime.split('/')[1]}"
        #     self.api.download_resource(resource.guid, resource_file)

        # return note

    async def trigger(self, entry_insertion_log: list[EntryInsertionLog]):
        # Get the sync state
        sync_state = self.api.get_sync_state()
        sync_count = sync_state.updateCount

        prev_sync_count = self.get_sync_state()
        if prev_sync_count == sync_count:
            logger.info(f"Sync count is the same, no new updates")
            return

        logger.info(f"Sync count is different, updating")
        self.set_sync_state(sync_count)

        updated_notebooks = self.get_updated_notebooks()
        logger.info(f"Updated notebooks: {updated_notebooks}")

        for notebook_id, notebook_name, notebook_last_updated, notebook_seq_num in updated_notebooks:
            # Get the updated notes
            updated_notes = self.get_updated_notes(notebook_id, notebook_last_updated)
            logger.info(f"Updated notes: {updated_notes}")
            for note_id, note_title, note_last_updated, note_seq_num in updated_notes:
                #### TESTING: ONLY PROCESSING ONE NOTE
                if note_title != "May 17, 2024":
                    continue
                #####

                logger.info(f"Processing note: {note_title}")
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_path = Path(temp_dir)
                    new_entries, to_remove_uuids = self.process_note(note_id, temp_path)

                    logger.info(f"{note_title}: Inserting {len(new_entries)} new entries and removing {len(to_remove_uuids)} old entries")

                    # Insert the new entries
                    for entry in new_entries:
                        if issubclass(entry.__class__, GenericFileEntry):
                            self.insert_file_entry(entry_insertion_log, entry)
                        else:
                            self.insert_entry(entry_insertion_log, entry)

                    # Remove the entries that are no longer in the note
                    for entry_uuid in to_remove_uuids:
                        self.emanager.delete_entry(entry_uuid)

                # Update the last update time
            #     self.set_note_update_data(note_id, notebook_id, note_last_updated, note_seq_num)
            # self.set_notebook_update_data(notebook_id, notebook_last_updated, notebook_seq_num)

    async def _on_trigger_interval(self, entry_insertion_log: list[EntryInsertionLog]):
        raise NotImplementedError

    async def _on_trigger_request(self, entry_insertion_log: list[EntryInsertionLog], file, metadata):
        await self.trigger(entry_insertion_log)

    async def _on_trigger_new_file(self, entry_insertion_log: list[EntryInsertionLog], file):
        raise NotImplementedError


