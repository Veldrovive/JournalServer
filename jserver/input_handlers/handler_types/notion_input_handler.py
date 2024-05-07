from notion_client import Client
from notion2markdown.notion import NotionClient
from notion2markdown.json2md import JsonToMdConverter
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
        # self.third_party_client = NotionClient(token=config.auth_token)  # Used to get the raw blocks
        # self.json_to_md_converter = JsonToMdConverter()

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

        self.blocks_collection = self.db_connection.get_collection("blocks")
        self.blocks_collection.create_index("id", unique=True)

    async def get_pages(self) -> tuple[NotionPage, list[NotionPage]]:
        """
        Finds the base Journal page and all the subpages

        The base Journal page must be a page with the title "Journal"
        Subpages are only those that are direct children of the base Journal page
        """
        pages = self.client.search()
        page_objs = [NotionPage(
            id = page["id"],
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

        return page_data["last_edited_time"] != page.last_edit_time_ms

    def set_page_processed(self, page: NotionPage):
        """
        Sets the last edited time of the page in the database
        """
        self.pages_collection.update_one({"id": page.id}, {"$set": {"last_edited_time": page.last_edit_time_ms}})

    async def process_day_page(self, page: NotionPage) -> NotionDayPage | None:
        """
        Processes a single day page

        Returns None if the page has not been updated
        """
        logger.info(f"Processing day page: {page.plaintext_title}")
        if not self.page_has_updated(page):
            return None
        logger.info(f"Page has been updated. Getting blocks")

        # blocks_res_json = get_page_blocks_json(self.client, page.id)

        # import json
        # with open("blocks.json", "w") as f:
        #     f.write(json.dumps(blocks_res_json, indent=2))

        blocks_res = get_page_blocks(self.client, page.id)
        blocks_res_json = [block.model_dump() for block in blocks_res]

        import json
        with open("blocks.json", "w") as f:
            f.write(json.dumps(blocks_res_json, indent=2))

        # raw_blocks = blocks_res["results"]
        # cur_block_ind = 0
        # blocks = []
        # while cur_block_ind < len(raw_blocks):
        #     block = raw_blocks[cur_block_ind]
        #     if block["type"] == "paragraph":
        #         # We just process the rich text to markdown and store it as a text entry
        #         raw_rich_text = block["paragraph"]["rich_text"]
        #         rich_text = [RichTextItem.validate(rich_text_item) for rich_text_item in raw_rich_text]
        #         markdown_text = process_rich_text(rich_text)


    def block_has_updated(self, block: NotionBlock) -> bool:
        """
        Checks the database to see if the last_edited_time of the block has changed
        If the block id is not found or the last_edited_time has changed, return True
        """
        block_data = self.blocks_collection.find_one({"id": block.id})
        if block_data is None:
            return True

        return block_data["last_edited_time"] != block.last_edit_time_ms

    def set_block_processed(self, block: NotionBlock):
        """
        Sets the last edited time of the block in the database
        """
        self.blocks_collection.update_one({"id": block.id}, {"$set": {"last_edited_time": block.last_edit_time_ms}})

    async def _on_trigger_interval(self, entry_insertion_log: list[EntryInsertionLog]):
        raise NotImplementedError

    async def _on_trigger_request(self, entry_insertion_log: list[EntryInsertionLog], file, metadata):
        journal_page, subpages = await self.get_pages()
        # logger.info(f"Journal page: {journal_page.model_dump_json(indent=2)}")
        # subpage_str = '\n'.join([subpage.model_dump_json(indent=2) for subpage in subpages])
        # logger.info(f"Subpages: {subpage_str}")
        # test_subpage = subpages[0]
        # Fine the page with the plaintext title: "Test"
        test_subpage = None
        for subpage in subpages:
            if subpage.plaintext_title == "Test":
                test_subpage = subpage
                break
        day_page = await self.process_day_page(test_subpage)

    async def _on_trigger_new_file(self, entry_insertion_log: list[EntryInsertionLog], file):
        raise NotImplementedError
