from notion_client import Client
from pydantic import BaseModel, Field
import datetime

from jserver.input_handlers.input_handler import InputHandler, EntryInsertionLog
from jserver.entries import Entry
from jserver.config.input_handler_config import NotionHandlerConfig
from jserver.utils.notion import *

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
        """
        page_data = self.pages_collection.find_one({"id": page.id})
        if page_data is None:
            return True

        # logger.info(f"Database page last edited time: {page_data['last_edited_time']}, Page last edit time: {page.last_edit_time_ms}")
        return page_data["last_edited_time"] != page.last_edit_time_ms

    def set_page_processed(self, page: NotionPage):
        """
        Sets the last edited time of the page in the database
        """
        self.pages_collection.replace_one({"id": page.id}, {"id": page.id, "last_edited_time": page.last_edit_time_ms}, upsert=True)

    async def process_day_page(self, page: NotionPage, start_time_ms: int, end_time_ms: int) -> list[NotionEntry]:
        """
        Processes all blocks on the page to notion entries which are directly convertible to Entry objects
        """
        logger.info(f"Processing day page: {page.plaintext_title}")
        logger.info(f"Getting blocks")
        blocks_res = get_page_blocks(self.client, page.id)
        try:
            logger.info(f"Splitting blocks")
            split_blocks = split_page_blocks(blocks_res, start_time_ms, end_time_ms, f"notion_page_{page.id}")
            logger.info(f"Got {len(split_blocks)} notion entries")
            logger.info("Resolving monotonicity")
            resolved_blocks = resolve_monotonicity(split_blocks, start_time_ms, end_time_ms)

            return resolved_blocks
        except Exception as e:
            raise e
        finally:
            logger.info(f"Cleaning up {len(blocks_res)} blocks")
            for block in blocks_res:
                block.cleanup()


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

        return block_data["last_edited_time"] != last_updated_time_ms

    def set_entry_processed(self, entry: NotionEntry, page: NotionPage):
        """
        Sets the last edited time of the entry in the database
        """
        id = entry.rep_uuid
        last_updated_time_ms = entry.last_updated_time
        page_id = page.id
        self.entries_collection.replace_one({"id": id}, {"id": id, "last_edited_time": last_updated_time_ms, "page_id": page_id}, upsert=True)

    async def trigger(self, entry_insertion_log: list[EntryInsertionLog]):
        journal_page, subpages = await self.get_pages()

        # # Find the page with the plaintext title: "Test"
        # test_subpage = None
        # for subpage in subpages:
        #     if subpage.plaintext_title == "Test":
        #         test_subpage = subpage
        #         break

        # if self.page_has_updated(test_subpage):
        #     logger.info(f"Test page has been updated. Getting blocks")
        #     new_notion_entries = await self.process_day_page(test_subpage, *test_subpage.get_day_bounds())
        #     logger.info(f"Got {len(new_notion_entries)} new notion entries")
        #     for notion_entry in new_notion_entries:
        #         # Check if the entry has been updated
        #         if self.entry_has_updated(notion_entry):
        #             entry = notion_entry_to_entry(notion_entry, self.handler_id)
        #             logger.info(f"Entry with id {notion_entry.rep_uuid} ({entry.entry_type}, {notion_entry.start_time}, {entry.start_time}) has been updated")
        #             if issubclass(entry.__class__, GenericFileEntry):
        #                 self.insert_file_entry(entry_insertion_log, entry)
        #             else:
        #                 self.insert_entry(entry_insertion_log, entry)
        #             self.set_entry_processed(notion_entry, test_subpage)
        #         else:
        #             logger.info(f"Entry with id {notion_entry.rep_uuid} has not been updated")
        #     self.set_page_processed(test_subpage)
        # else:
        #     logger.info(f"Test page has not been updated")

        not_updated_list = []
        updated_list = []
        for subpage in subpages:
            if self.page_has_updated(subpage):
                day_start_ms, day_end_ms = subpage.get_day_bounds()
                logger.info(f"Subpage {subpage.plaintext_title} ({day_start_ms} - {day_end_ms}) has been updated. Getting blocks")
                new_notion_entries = await self.process_day_page(subpage, day_start_ms, day_end_ms)
                logger.info(f"Got {len(new_notion_entries)} new notion entries")
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
                        logger.info(f"Entry with id {notion_entry.rep_uuid} has not been updated")
                self.set_page_processed(subpage)
                updated_list.append(subpage.plaintext_title)
            else:
                # logger.info(f"Subpage {subpage.plaintext_title} has not been updated")
                not_updated_list.append(subpage.plaintext_title)
        if len(not_updated_list) > 0:
            if len(not_updated_list) == len(subpages):
                logger.info(f"All subpages have not been updated")
            else:
                logger.info(f"Subpages {not_updated_list} have not been updated")
        if len(updated_list) > 0:
            logger.info(f"Subpages {updated_list} have been updated")

    async def _on_trigger_interval(self, entry_insertion_log: list[EntryInsertionLog]):
        await self.trigger(entry_insertion_log)

    async def _on_trigger_request(self, entry_insertion_log: list[EntryInsertionLog], file, metadata):
        await self.trigger(entry_insertion_log)

    async def _on_trigger_new_file(self, entry_insertion_log: list[EntryInsertionLog], file):
        raise NotImplementedError
