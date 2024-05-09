from notion_client import Client
from pydantic import BaseModel, Field
import datetime

from jserver.input_handlers.input_handler import InputHandler, EntryInsertionLog
from jserver.entries import Entry
from jserver.config.input_handler_config import NotionHandlerConfig
from jserver.utils.notion import *
from jserver.exceptions import *

from jserver.utils.logger import setup_logging
logger = setup_logging(__name__)

from typing import Callable

def process_rich_text(rich_text: list[RichTextItem]):
    """
    Processes a list of rich text items into markdown

    This is a very basic implementation that only handles text and links
    """
    markdown_text = ""
    for item in rich_text:
        if item["type"] == "text":
            markdown_text += item["text"]["content"]
        elif item["type"] == "link":
            markdown_text += f"[{item['link']['url']}]({item['link']['url']})"
    return markdown_text

class NotionInputHandler(InputHandler):
    _requires_db_connection = True
    _requires_input_folder = False
    _takes_file_input = False

    def __init__(self, handler_id: str, config: NotionHandlerConfig, on_entries_inserted: Callable[[list[EntryInsertionLog]], None], db_connection):
        super().__init__(handler_id, config, on_entries_inserted, db_connection)
        self.config = config

        self.client = Client(auth=config.auth_token)

        self.init_database()

    def init_database(self):
        """
        Creates two new collections.
        1. Pages: Stores page ids and the corresponding last edited time
        2. Blocks: Stores block ids and the corresponding last edited time

        Both have an index on the id field
        """
        self.pages_collection = self.db_connection.get_collection("pages")
        self.pages_collection.create_index("id", unique=True)

        self.entries_collection = self.db_connection.get_collection("blocks")
        self.entries_collection.create_index("id", unique=True)
        self.entries_collection.create_index("page_id", unique=False)

    async def get_pages(self) -> tuple[NotionPage, list[NotionPage]]:
        """
        Finds the base Journal page and all the subpages

        The base Journal page must be a page with the title "Journal"
        Subpages are only those that are direct children of the base Journal page
        """
        pages = self.client.search()

        page_objs = [NotionPage(
            id = page["id"],
            created_time = page["created_time"],
            last_edited_time = page["last_edited_time"],
            parent_page_id = page["parent"]["page_id"] if page["parent"]["type"] == "page_id" else None,
            plaintext_title = page["properties"]["title"]["title"][0]["plain_text"],
            url = page["url"]
        ) for page in pages["results"]]

        # Find the base Journal page
        journal_page = None
        for page in page_objs:
            if page.plaintext_title == "Journal":
                journal_page = page
                break

        if journal_page is None:
            raise ValueError("Could not find the Journal page")

        # Find the subpages
        subpages = [page for page in page_objs if page.parent_page_id == journal_page.id]

        return journal_page, subpages

    def page_has_updated(self, page: NotionPage) -> bool:
        """
        Checks the database to see if the last_edited_time of the page has changed
        If the page id is not found or the last_edited_time has changed, return True

        Returns a tuple of two booleans:
        1. Whether the page has been updated
        2. Whether this is due to a recheck interval timeout. This is used to ensure we don't get into a loop of rechecking.
        """
        page_data = self.pages_collection.find_one({"id": page.id})
        if page_data is None:
            return True, False

        logger.debug(f"Database page last edited time: {page_data['last_edited_time']}, Page last edit time: {page.last_edit_time_ms}")
        if page_data["last_edited_time"] != page.last_edit_time_ms:
            return True, False

        # If the page has the "recheck_time" field and the current time is greater than that, then we should recheck
        if "recheck_time" in page_data and page_data["recheck_time"] != 0:
            current_time_ms = datetime.datetime.now().timestamp() * 1000
            if current_time_ms > page_data["recheck_time"]:
                # Update the database to set the recheck time to 0 so we don't recheck again
                logger.info(f"Updating page due to recheck timeout \"{page.plaintext_title}\" ({page.id})")
                self.pages_collection.update_one({"id": page.id}, {"$set": {"recheck_time": 0}})
                return True, True

        return False, False

    def set_page_processed(self, page: NotionPage, should_set_recheck=True):
        """
        Sets the last edited time of the page in the database
        """
        current_time_ms = datetime.datetime.now().timestamp() * 1000
        recheck_time_ms = current_time_ms + self.config.recheck_interval * 1000 if should_set_recheck else 0

        logger.info(f"Setting page \"{page.plaintext_title}\" ({page.id}) as processed with recheck time {recheck_time_ms}")
        self.pages_collection.replace_one(
            {"id": page.id},
            {
                "id": page.id,
                "last_edited_time": page.last_edit_time_ms,
                "recheck_time": recheck_time_ms,
            },
            upsert=True
        )

    def entry_has_updated(self, entry: NotionEntry) -> bool:
        """
        Checks the database to see if the last_edited_time of the entry has changed
        If the entry id is not found or the last_edited_time has changed, return True
        """
        id = entry.rep_uuid
        last_updated_time_ms = entry.last_updated_time
        block_data = self.entries_collection.find_one({"id": id})
        if block_data is None:
            return True

        if "data_hash" in block_data:
            # If the data has has changed we should reprocess the entry
            new_data_hash = entry.data_hash
            if new_data_hash != block_data["data_hash"]:
                logger.info(f"Data hash has changed for entry {id}. Re-processing")
                return True

        return block_data["last_edited_time"] != last_updated_time_ms

    def set_entry_processed(self, entry: NotionEntry, page: NotionPage):
        """
        Sets the last edited time of the entry in the database
        """
        id = entry.rep_uuid
        last_updated_time_ms = entry.last_updated_time
        page_id = page.id
        data_hash = entry.data_hash
        self.entries_collection.replace_one(
            {"id": id},
            {
                "id": id,
                "last_edited_time": last_updated_time_ms,
                "page_id": page_id,
                "data_hash": data_hash
            },
            upsert=True
        )

    def remove_entry(self, rep_uuid: str):
        """
        Removes the entry from the database. This is done along with emanager removing the entry object from the main database.
        """
        self.entries_collection.delete_one({"id": rep_uuid})

    def get_stored_page_blocks(self, page: NotionPage) -> list[str]:
        """
        Returns the rep_uuids of all the blocks on the page from the database
        """
        blocks = self.entries_collection.find({"page_id": page.id})
        return [block["id"] for block in blocks]

    async def process_day_page(self, page: NotionPage, start_time_ms: int, end_time_ms: int) -> list[NotionEntry]:
        """
        Processes all blocks on the page to notion entries which are directly convertible to Entry objects
        """
        logger.info(f"Processing day page: {page.plaintext_title}")
        logger.info(f"Getting blocks")
        blocks_res = get_page_blocks(self.client, page.id)

        logger.info(f"Splitting blocks")
        split_blocks = split_page_blocks(blocks_res, start_time_ms, end_time_ms, f"notion_page_{page.id}")
        logger.info(f"Got {len(split_blocks)} notion entries")
        logger.info("Resolving monotonicity")
        resolved_blocks = resolve_monotonicity(split_blocks, start_time_ms, end_time_ms)

        # We also want to get a list of all blocks that previously existed, but no longer do
        new_block_ids = set([block.rep_uuid for block in resolved_blocks])
        previous_block_ids = set(self.get_stored_page_blocks(page))
        removed_block_ids = previous_block_ids - new_block_ids

        return blocks_res, resolved_blocks, removed_block_ids

    async def try_create_day_page(self, journal_page: NotionPage, existing_subpages: list[NotionPage]):
        """
        As a convenience function, if there is no existing subpage with the current day's date, create one
        """
        if not self.config.auto_generate_today_page:
            return

        today = datetime.datetime.now()
        today_str = today.strftime("%Y-%m-%d")

        for subpage in existing_subpages:
            page_datetime = subpage.get_day_date()
            page_date_str = page_datetime.strftime("%Y-%m-%d")

            logger.debug(f"Checking subpage \"{subpage.plaintext_title}\" ({page_date_str} vs {today_str})")
            if page_date_str == today_str:
                logger.info(f"Today's page already exists")
                return
        logger.info(f"Creating today's page")

        # Construct the page title (e.g. "April 2, 2000")
        page_title = today.strftime("%B%e, %Y")

        res = self.client.pages.create(
            parent={"page_id": journal_page.id, "type": "page_id"},
            properties={
                "title": {
                    "type": "title",
                    "title": [
                        {
                            "type": "text",
                            "text": {
                                "content": page_title
                            }
                        }
                    ]
                }
            }
        )

    async def trigger(self, entry_insertion_log: list[EntryInsertionLog]):
        journal_page, subpages = await self.get_pages()

        await self.try_create_day_page(journal_page, subpages)

        if self.config.testing:
            # Then we only want to use pages that start with "Test"
            logger.warning(f"Using testing pages only")
            target_subpages = [page for page in subpages if page.plaintext_title.startswith("Test")]
        else:
            # Then we only want to use pages that do not start with "Test"
            target_subpages = [page for page in subpages if not page.plaintext_title.startswith("Test")]

        not_updated_list = []
        updated_list = []
        raw_blocks = []
        try:
            for subpage in target_subpages:
                should_update, is_recheck = self.page_has_updated(subpage)
                if should_update:
                    day_start_ms, day_end_ms = subpage.get_day_bounds()
                    logger.info(f"Subpage {subpage.plaintext_title} ({day_start_ms} - {day_end_ms}) has been updated. Getting blocks")
                    raw_blocks, new_notion_entries, removed_block_rep_ids = await self.process_day_page(subpage, day_start_ms, day_end_ms)
                    logger.info(f"Inserting {len(new_notion_entries)} new notion entries")
                    for notion_entry in new_notion_entries:
                        # Check if the entry has been updated
                        if self.entry_has_updated(notion_entry):
                            logger.info(f"Entry with id {notion_entry.rep_uuid} has been updated")
                            entry = notion_entry_to_entry(notion_entry, self.handler_id)
                            if issubclass(entry.__class__, GenericFileEntry):
                                self.insert_file_entry(entry_insertion_log, entry)
                            else:
                                self.insert_entry(entry_insertion_log, entry)
                            self.set_entry_processed(notion_entry, subpage)
                        else:
                            logger.debug(f"Entry with id {notion_entry.rep_uuid} has not been updated")

                    logger.info(f"Removing {len(removed_block_rep_ids)} entries")
                    for rep_uuid in removed_block_rep_ids:
                        logger.info(f"Removing entry with id {rep_uuid}")
                        try:
                            self.emanager.delete_entry(rep_uuid)
                            self.remove_entry(rep_uuid)
                        except EntryNotFoundException:
                            logger.warning(f"Failed to delete entry with id {rep_uuid} as it does not exist")
                            # In this case we still want to remove the entry from the database
                            self.remove_entry(rep_uuid)

                    self.set_page_processed(subpage, should_set_recheck=not is_recheck)
                    updated_list.append(subpage.plaintext_title)
                else:
                    # logger.info(f"Subpage {subpage.plaintext_title} has not been updated")
                    not_updated_list.append(subpage.plaintext_title)
            if len(not_updated_list) > 0:
                if len(not_updated_list) == len(target_subpages):
                    logger.info(f"All subpages have not been updated")
                else:
                    logger.info(f"Subpages {not_updated_list} have not been updated")
            if len(updated_list) > 0:
                logger.info(f"Subpages {updated_list} have been updated")
        except Exception as e:
            raise e
        finally:
            logger.info(f"Cleaning up {len(raw_blocks)} blocks")
            for block in raw_blocks:
                block.cleanup()  # Deletes the temporary files

    async def _on_trigger_interval(self, entry_insertion_log: list[EntryInsertionLog]):
        await self.trigger(entry_insertion_log)

    async def _on_trigger_request(self, entry_insertion_log: list[EntryInsertionLog], file, metadata):
        await self.trigger(entry_insertion_log)

    async def _on_trigger_new_file(self, entry_insertion_log: list[EntryInsertionLog], file):
        raise NotImplementedError
