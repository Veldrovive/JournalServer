import datetime
from contextlib import contextmanager
import tempfile
import pathlib
import urllib
import requests
import os
import re

import dateutil.parser
from pydantic import BaseModel, Field, ValidationError, computed_field
from notion_client import Client
from notion_client.helpers import iterate_paginated_api as paginate

from jserver.entries import Entry, TextEntry, GenericFileEntry, ImageFileEntry, VideoFileEntry, AudioFileEntry, PDFileEntry
from jserver.utils.file_metadata import extract_file_metadata
from jserver.utils.hashers import *

from jserver.utils.logger import setup_logging
logger = setup_logging(__name__)

from typing import Literal, Any, ClassVar

class RichTextLink(BaseModel):
    url: str = Field(..., description="The url of the link")

class RichTextText(BaseModel):
    content: str = Field(..., description="The content of the text")
    link: RichTextLink | None = Field(None, description="The link of the text")

class RichTextEquation(BaseModel):
    expression: str = Field(..., description="The latex expression of the equation")

class RichTextAnnotations(BaseModel):
    bold: bool
    italic: bool
    strikethrough: bool
    underline: bool
    code: bool
    color: str | None = None

class RichTextItem(BaseModel):
    # type: Literal["text"] = "text"
    # text: RichTextText
    annotations: RichTextAnnotations
    plain_text: str
    href: str | None = None

    def to_markdown(self) -> str:
        """
        Converts the rich text item to markdown
        """
        markdown = self.plain_text
        # Get the amount of white space on the left and right
        left_whitespace = len(markdown) - len(markdown.lstrip())
        right_whitespace = len(markdown) - len(markdown.rstrip())
        markdown = markdown.strip()
        if self.href is not None:
            markdown = f"[{markdown}]({self.href})"
        if self.annotations.bold:
            markdown = f"**{markdown}**"
        if self.annotations.italic:
            markdown = f"*{markdown}*"
        if self.annotations.strikethrough:
            markdown = f"~~{markdown}~~"
        if self.annotations.underline:
            markdown = f"<u>{markdown}</u>"
        if self.annotations.code:
            markdown = f"`{markdown}`"
        # Add back the white space
        markdown = " " * left_whitespace + markdown + " " * right_whitespace
        return markdown

class TextRichTextItem(RichTextItem):
    type: Literal["text"] = "text"
    text: RichTextText

class EquationRichTextItem(RichTextItem):
    type: Literal["equation"] = "equation"
    equation: RichTextEquation

    def to_markdown(self) -> str:
        """
        Converts the rich text item to markdown
        """
        return f"${self.equation.expression}$"

class NotionPage(BaseModel):
    id: str = Field(..., description="The id of the page")
    created_time: str = Field(..., description="The created time of the page. ISO format 2024-05-05T21:55:00.000Z")
    last_edited_time: str = Field(..., description="The last edited time of the page. ISO format 2024-05-05T21:55:00.000Z")
    parent_page_id: str | None = Field(None, description="The id of the parent page. None if the parent is not a page")
    plaintext_title: str = Field(..., description="The plaintext title of the page")
    url: str = Field(..., description="The url of the page")

    @computed_field
    @property
    def last_edit_time_ms(self) -> int:
        """
        Returns the last edit time in milliseconds
        """
        return int(dateutil.parser.parse(self.last_edited_time).timestamp() * 1000)

    @computed_field
    @property
    def created_time_ms(self) -> int:
        """
        Returns the created time in milliseconds
        """
        return int(dateutil.parser.parse(self.created_time).timestamp() * 1000)

    def get_day_date(self) -> datetime.datetime:
        """
        If the title has the format "[MONTH] [DAY], [YEAR]", then we can use that to get the date
        If not then we use the created time
        """
        tzinfo = datetime.datetime.now().astimezone().tzinfo
        match = re.match(r"(\w+) +(\d+),? +(\d+)", self.plaintext_title)
        if match is not None:
            month, day, year = match.groups()
            day = int(day)
            year = int(year)
            if year < 1000:  # You probably aren't inventing algebra right now
                year += 2000
            month = datetime.datetime.strptime(month, "%B").month
            created_time_dt = datetime.datetime(year, month, day, tzinfo=tzinfo)
            start_time = created_time_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            created_time_dt = datetime.datetime.fromtimestamp(self.created_time_ms / 1000, tz=tzinfo)
            start_time = created_time_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        return start_time

    def get_day_bounds(self) -> tuple[int, int]:
        """
        Returns the ms since the epoch for the start and end of the day
        Assumes that the timezone is the same as the current timezone
        """
        day_date = self.get_day_date()
        start_time = int(day_date.timestamp() * 1000)
        end_time = int((day_date + datetime.timedelta(days=1) - datetime.timedelta(microseconds=1)).timestamp() * 1000)
        return start_time, end_time

class NotionBlock(BaseModel):
    object: Literal["block"] = "block"
    id: str = Field(..., description="The id of the block")
    created_time: str = Field(..., description="The created time of the block. ISO format 2024-05-05T21:55:00.000Z")
    last_edited_time: str = Field(..., description="The last edited time of the block. ISO format 2024-05-05T21:55:00.000Z")
    type: str = Field(..., description="The type of the block")

    @computed_field
    @property
    def last_edit_time_ms(self) -> int:
        """
        Returns the last edit time in milliseconds
        """
        return int(dateutil.parser.parse(self.last_edited_time).timestamp() * 1000)

    @computed_field
    @property
    def created_time_ms(self) -> int:
        """
        Returns the created time in milliseconds
        """
        return int(dateutil.parser.parse(self.created_time).timestamp() * 1000)

    @property
    def data_hash(self) -> str:
        """
        Returns a hash of the data of the block.
        Used to check for small changes within a minute that dont effect the last edited time
        This is a notion API quirk that means we need an alternative way to check if the block has changed besides the last edited time
        """
        return ""

    def cleanup(self):
        """
        Cleans up any temporary files
        """
        pass

AllRichTextItems = TextRichTextItem | EquationRichTextItem


######### Notion Block Type Definitions #########
class NotionRichTextData(BaseModel):
    rich_text: list[AllRichTextItems] = Field([], description="Rich text JSON", exclude=True)
    color: str | None = Field(None, description="The color of the text")

    @computed_field
    @property
    def markdown_text(self) -> str:
        """
        Converts the rich text to markdown
        """
        return "".join([item.to_markdown() for item in self.rich_text])

class NotionParagraphBlock(NotionBlock):
    _type: ClassVar[str] = "paragraph"
    type: Literal["paragraph"] = "paragraph"
    paragraph: NotionRichTextData = Field(..., description="The paragraph data of the block")

    @property
    def data_hash(self) -> str:
        return hash_text(self.paragraph.markdown_text)

class NotionHeadingOneBlock(NotionBlock):
    _type: ClassVar[str] = "heading_1"
    type: Literal["heading_1"] = "heading_1"
    heading_1: NotionRichTextData = Field(..., description="The heading 1 data of the block")

    @property
    def data_hash(self) -> str:
        return hash_text(self.heading_1.markdown_text)

class NotionHeadingTwoBlock(NotionBlock):
    _type: ClassVar[str] = "heading_2"
    type: Literal["heading_2"] = "heading_2"
    heading_2: NotionRichTextData = Field(..., description="The heading 2 data of the block")

    @property
    def data_hash(self) -> str:
        return hash_text(self.heading_2.markdown_text)

class NotionHeadingThreeBlock(NotionBlock):
    _type: ClassVar[str] = "heading_3"
    type: Literal["heading_3"] = "heading_3"
    heading_3: NotionRichTextData = Field(..., description="The heading 3 data of the block")

    @property
    def data_hash(self) -> str:
        return hash_text(self.heading_3.markdown_text)

class NotionBulletedListBlock(NotionBlock):
    _type: ClassVar[str] = "bulleted_list_item"
    type: Literal["bulleted_list_item"] = "bulleted_list_item"
    bulleted_list_item: NotionRichTextData = Field(..., description="The bulleted list data of the block")

    @property
    def data_hash(self) -> str:
        return hash_text(self.bulleted_list_item.markdown_text)

class NotionNumberedListBlock(NotionBlock):
    _type: ClassVar[str] = "numbered_list_item"
    type: Literal["numbered_list_item"] = "numbered_list_item"
    numbered_list_item: NotionRichTextData = Field(..., description="The numbered list data of the block")

    @property
    def data_hash(self) -> str:
        return hash_text(self.numbered_list_item.markdown_text)

class NotionQuoteBlock(NotionBlock):
    _type: ClassVar[str] = "quote"
    type: Literal["quote"] = "quote"
    quote: NotionRichTextData = Field(..., description="The quote data of the block")

    @property
    def data_hash(self) -> str:
        return hash_text(self.quote.markdown_text)

class NotionFileData(BaseModel):
    caption: list[AllRichTextItems] = Field([], description="The caption of the image", exclude=True)
    type: str = Field(..., description="file or external")
    external: dict[str, str] | None = Field(None, description="The external data of the image. None if the image is a file. Contains only `url` key.")
    file: dict[str, str] | None = Field(None, description="The file data of the image. None if the image is external. Contains `url` and `expiry_time` keys.")
    name: str | None = Field(None, description="The name of the file")

    temp_file_data: dict[str, Any] | None = Field(None, description="Temporary file data for the file", exclude=True)

    @computed_field
    @property
    def markdown_caption(self) -> str:
        """
        Converts the caption to markdown
        """
        return "".join([item.to_markdown() for item in self.caption])

    def pull_file(self) -> dict[str, Any]:
        """
        Downloads the file as a temporary file and returns the temp file data
        {
            file: tempfile,
            name: str,  ("test.ext")
            type: str (".ext")
        }
        """
        if self.temp_file_data:
            return self.temp_file_data

        file_url = self.file["url"] if self.type == "file" else self.external["url"]
        name = None
        if self.name:
            name = self.name
        else:
            # Then we need to get the name based on the url
            name = pathlib.Path(urllib.parse.urlparse(file_url).path).name
        if name:
            ext = pathlib.Path(name).suffix

        # Create a temporary file with the correct extension
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as temp_file:
            response = requests.get(file_url)
            temp_file.write(response.content)
            temp_file.seek(0)

            self.temp_file_data = {
                "file": temp_file,
                "name": name,
                "type": ext
            }
            return self.temp_file_data

    def get_file_metadata(self) -> tuple[datetime.datetime, dict, int]:
        """
        Returns a tuple of the creation time, {lat, lng}, and duration_ms of the file
        """
        file_data = self.pull_file()
        return extract_file_metadata(file_data["file"].name)

    def remove_temp_file(self):
        if self.temp_file_data:
            os.unlink(self.temp_file_data["file"].name)
            self.temp_file_data = None

    def __del__(self):
        self.remove_temp_file()


class NotionImageBlock(NotionBlock):
    _type: ClassVar[str] = "image"
    type: Literal["image"] = "image"
    image: NotionFileData = Field(..., description="The image data of the block")

    @property
    def data_hash(self) -> str:
        """
        We has the caption text along with the file type
        We can't hash the url because it changes every time the file is downloaded
        """
        return hash_text(self.image.markdown_caption + self.image.type)

    def cleanup(self):
        self.image.remove_temp_file()

class NotionVideoBlock(NotionBlock):
    _type: ClassVar[str] = "video"
    type: Literal["video"] = "video"
    video: NotionFileData = Field(..., description="The video data of the block")

    @property
    def data_hash(self) -> str:
        """
        We has the caption text along with the file type
        We can't hash the url because it changes every time the file is downloaded
        """
        return hash_text(self.video.markdown_caption + self.video.type)

    def cleanup(self):
        self.video.remove_temp_file()

class NotionAudioBlock(NotionBlock):
    _type: ClassVar[str] = "audio"
    type: Literal["audio"] = "audio"
    audio: NotionFileData = Field(..., description="The audio data of the block")

    @property
    def data_hash(self) -> str:
        """
        We has the caption text along with the file type
        We can't hash the url because it changes every time the file is downloaded
        """
        return hash_text(self.audio.markdown_caption + self.audio.type)

    def cleanup(self):
        self.audio.remove_temp_file()

class NotionGenericFileBlock(NotionBlock):
    _type: ClassVar[str] = "file"
    type: Literal["file"] = "file"
    file: NotionFileData = Field(..., description="The file data of the block")

    @property
    def data_hash(self) -> str:
        """
        We has the caption text along with the file type
        We can't hash the url because it changes every time the file is downloaded
        """
        return hash_text(self.file.markdown_caption + self.file.type)

    def cleanup(self):
        self.file.remove_temp_file()

class NotionEquationData(BaseModel):
    expression: str = Field(..., description="The latex expression of the equation")

class NotionEquationBlock(NotionBlock):
    _type: ClassVar[str] = "equation"
    type: Literal["equation"] = "equation"
    equation: NotionEquationData = Field(..., description="The equation data of the block")

    @property
    def data_hash(self) -> str:
        return hash_text(self.equation.expression)

class NotionCodeData(BaseModel):
    caption: list[AllRichTextItems] = Field([], description="The caption of the code block", exclude=True)
    rich_text: list[AllRichTextItems] = Field([], description="The rich text of the code block", exclude=True)
    language: str | None = Field(None, description="The language of the code block")

    @computed_field
    @property
    def markdown_text(self) -> str:
        """
        Converts the rich text to markdown
        """
        return "".join([item.to_markdown() for item in self.rich_text])

    @computed_field
    @property
    def markdown_caption(self) -> str:
        """
        Converts the caption to markdown
        """
        return "".join([item.to_markdown() for item in self.caption])

class NotionCodeBlock(NotionBlock):
    _type: ClassVar[str] = "code"
    type: Literal["code"] = "code"
    code: NotionCodeData = Field(..., description="The code data of the block")

    @property
    def data_hash(self) -> str:
        return hash_text(self.code.markdown_text + self.code.language)

ArbitraryNotionBlockType = NotionParagraphBlock | NotionHeadingOneBlock | NotionHeadingTwoBlock | NotionHeadingThreeBlock | \
    NotionBulletedListBlock | NotionNumberedListBlock | NotionQuoteBlock | NotionImageBlock | NotionVideoBlock | \
    NotionAudioBlock | NotionGenericFileBlock | NotionEquationBlock | NotionCodeBlock

AllNotionBlockTypes = [NotionImageBlock, NotionBulletedListBlock, NotionNumberedListBlock, NotionHeadingThreeBlock, NotionHeadingTwoBlock,
    NotionHeadingOneBlock, NotionParagraphBlock, NotionVideoBlock, NotionAudioBlock, NotionGenericFileBlock,
    NotionEquationBlock, NotionCodeBlock, NotionQuoteBlock]
###########################################

class NotionEntry(BaseModel):
    """
    Associates a list of blocks that can be converted into a single entry with a start time, duration,
    and representative id for the entire set of blocks
    """
    rep_uuid: str = Field(..., description="The representative UUID of the entry")
    group_id: str = Field(..., description="The group id of the entry")
    start_time: int = Field(..., description="The start time of the entry in milliseconds since the epoch")
    last_updated_time: int = Field(..., description="The latest time any of the constituent blocks were updated in ms since the epoch")
    duration: int | None = Field(None, description="The duration of the entry in milliseconds")
    latitude: float | None = Field(None, description="The latitude of the entry")
    longitude: float | None = Field(None, description="The longitude of the entry")
    seq_id: int | None = Field(None, description="Defines where in a group the entry should be placed. Should be unique within a group")
    notion_blocks: list[ArbitraryNotionBlockType] = Field([], description="The blocks of the entry")

    @property
    def data_hash(self) -> str:
        """
        Returns a combined hash of the data of the entry and the sequence id
        """
        return hash_text("".join([block.data_hash for block in self.notion_blocks]) + str(self.seq_id))

def create_notion_entry(blocks: list[NotionBlock], seq_id: int, group_id: str, start_time_override: int | None = None):
    """
    Uses the content of the notion blocks to find the values of the notion entry metadata
    """
    logger.debug(f"Creating notion entry with {len(blocks)} blocks", [block.type for block in blocks])
    # The representative UUID is the type of the first block "_" id of the first block
    rep_uuid = f"{blocks[0].type}_{blocks[0].id}"

    # The start time varies based on the entry type
    # We default to the start time of the first block
    # Later when we process a file we will override this with the file metadata time if it exists
    start_time = blocks[0].created_time_ms if start_time_override is None else start_time_override

    # Duration is None for now
    duration = None

    # Latitude and longitude are None for now
    latitude = None
    longitude = None

    # Check if the first block is a file
    if blocks[0].type in ["file", "image", "video", "audio"]:
        # Then we need to get the metadata of the file
        file_data = None
        if blocks[0].type == "file":
            file_data = blocks[0].file
        elif blocks[0].type == "image":
            file_data = blocks[0].image
        elif blocks[0].type == "video":
            file_data = blocks[0].video
        elif blocks[0].type == "audio":
            file_data = blocks[0].audio

        file_start_time, file_location, file_duration_ms = file_data.get_file_metadata()
        if file_start_time is not None and start_time_override is None:
            start_time = int(file_start_time.timestamp() * 1000)

        if file_location is not None:
            latitude, longitude = file_location["lat"], file_location["lng"]

        if file_duration_ms is not None:
            duration = file_duration_ms

    last_updated_time = max([block.last_edit_time_ms for block in blocks])

    logger.debug(f"Start time: {start_time}, duration: {duration}, latitude: {latitude}, longitude: {longitude}, seq_id: {seq_id}")
    return NotionEntry(
        rep_uuid=rep_uuid,
        group_id=group_id,
        start_time=start_time,
        last_updated_time=last_updated_time,
        duration=duration,
        latitude=latitude,
        longitude=longitude,
        seq_id=seq_id,
        notion_blocks=blocks
    )

def get_page_blocks_json(client: Client, page_block_id: str) -> list[dict[str, Any]]:
    """
    Retrieves a list of all block objects that are children of the block with id page_block_id
    """
    return list(paginate(client.blocks.children.list, block_id=page_block_id))

def get_page_blocks(client: Client, page_block_id: str) -> list[NotionBlock]:
    """
    Retrieves a list of all block objects that are children of the block with id page_block_id
    """
    blocks_json = get_page_blocks_json(client, page_block_id)
    blocks = []
    # blocks = [(NotionBlockContainer.validate(block)).block for block in blocks_json]
    for i, block_json in enumerate(blocks_json):
        for block_type in AllNotionBlockTypes:
            if block_json["type"] == block_type._type:
                try:
                    blocks.append(block_type.validate(block_json))
                    break
                except ValidationError as e:
                    import json
                    logger.warning(f"Error validating block {i}: {json.dumps(block_json, indent=2)}")
                    raise e
        else:
            # Skip the block and log an error
            import json
            logger.error(f"Could not find block type for block {i}: {json.dumps(block_json, indent=2)}")
            # raise ValueError(f"Block type {block_json['type']} not recognized")

    return blocks

# We define a block type cluster as a set of block type ids such that all can be included in a single entry
# For example, all purely text blocks may be included in a single entry
block_type_clusters = [
    ['paragraph', 'heading_1', 'heading_2', 'heading_3', 'bulleted_list_item', 'numbered_list_item', 'quote', 'code', 'equation'],
    ['image'],
    ['video'],
    ['audio'],
    ['file']
]

# We also define whether each cluster type is allowed to be clustered together into a single entry
# Files are not clustered, but text may be
clustering_allowed = [
    True,
    False,
    False,
    False,
    False
]

def get_cluster_idx(block_type: str) -> int:
        for i, cluster in enumerate(block_type_clusters):
            if block_type in cluster:
                return i
        raise ValueError(f"Block type {block_type} not recognized")

def parse_date_block(text: str) -> int | None:
    """
    If the string is H:MM or HH:MM, optionally followed by :SS (seconds), then we return the time in milliseconds since the epoch.
    We also accept (H)H:MM:SS AM/PM or (H)H:MM:SSAM/PM. AM and PM may or may not be capitalized.

    Returns an offset in milliseconds since the start of the day.
    """
    match = re.match(r"(\d{1,2}):(\d{2})(?::(\d{2}))?\s?(AM|PM|am|pm)?", text, re.IGNORECASE)
    if match is None:
        return None
    hour, minute, seconds, am_pm = match.groups()
    hour = int(hour)
    minute = int(minute)
    seconds = int(seconds) if seconds is not None else 0  # Default to 0 if seconds are not provided

    if am_pm:
        am_pm = am_pm.lower()  # Normalize to lowercase for comparison
        if am_pm == "pm" and hour != 12:
            hour += 12
        elif am_pm == "am" and hour == 12:
            hour = 0  # Midnight case

    return (hour * 3600 + minute * 60 + seconds) * 1000

def notion_entry_to_entry(notion_entry: NotionEntry, handler_id: str) -> Entry:
    """
    Converts a notion entry to an entry
    """
    # How we convert the entry is dependent on the cluster type
    data = None
    entry_constructor = None
    cluster_type = get_cluster_idx(notion_entry.notion_blocks[0].type)
    if cluster_type == 0:
        # Then we are dealing with all text. We will create a text entry.
        text = ""
        num_list_num = 1
        for i, block in enumerate(notion_entry.notion_blocks):
            should_markdown_newline = True
            new_text = ""
            if block.type == "paragraph":
                new_text = block.paragraph.markdown_text
            elif block.type == "heading_1":
                new_text = "# " + block.heading_1.markdown_text
            elif block.type == "heading_2":
                new_text = "## " + block.heading_2.markdown_text
            elif block.type == "heading_3":
                new_text = "### " + block.heading_3.markdown_text
            elif block.type == "bulleted_list_item":
                new_text = "- " + block.bulleted_list_item.markdown_text
                should_markdown_newline = False
            elif block.type == "numbered_list_item":
                new_text = f"{num_list_num}. " + block.numbered_list_item.markdown_text
                num_list_num += 1
                should_markdown_newline = False
            elif block.type == "quote":
                new_text = "> " + block.quote.markdown_text
            elif block.type == "code":
                new_text = "```" + block.code.language + "\n" + block.code.markdown_text + "\n```"
            elif block.type == "equation":
                new_text = "$$" + block.equation.expression + "$$"
            if i > 0:
                if should_markdown_newline:
                    text += "\n\n"  # markdown new line between blocks
                else:
                    text += "\n"
            text += new_text
        data = text
        entry_constructor = TextEntry
    elif cluster_type == 1:
        block = notion_entry.notion_blocks[0]
        file_data = block.image.pull_file()
        file_detail = ImageFileEntry.generate_file_detail(
            file_path = file_data["file"].name,
            file_metadata = {},
            use_path_as_id = True  # Set this way until the file is uploaded to the file store
        )
        if file_data["name"]:
            file_detail.file_name = file_data["name"]
        data = file_detail
        entry_constructor = ImageFileEntry
    elif cluster_type == 2:
        block = notion_entry.notion_blocks[0]
        file_data = block.video.pull_file()
        file_detail = VideoFileEntry.generate_file_detail(
            file_path = file_data["file"].name,
            file_metadata = {},
            use_path_as_id = True  # Set this way until the file is uploaded to the file store
        )
        if file_data["name"]:
            file_detail.file_name = file_data["name"]
        data = file_detail
        entry_constructor = VideoFileEntry
    elif cluster_type == 3:
        block = notion_entry.notion_blocks[0]
        file_data = block.audio.pull_file()
        file_detail = AudioFileEntry.generate_file_detail(
            file_path = file_data["file"].name,
            file_metadata = {},
            use_path_as_id = True  # Set this way until the file is uploaded to the file store
        )
        if file_data["name"]:
            file_detail.file_name = file_data["name"]
        data = file_detail
        entry_constructor = AudioFileEntry
    elif cluster_type == 4:
        block = notion_entry.notion_blocks[0]
        file_data = block.file.pull_file()
        file_detail = GenericFileEntry.generate_file_detail(
            file_path = file_data["file"].name,
            file_metadata = {},
            use_path_as_id = True  # Set this way until the file is uploaded to the file store
        )
        if file_data["name"]:
            file_detail.file_name = file_data["name"]
        data = file_detail
        if file_data["type"].lower() == ".pdf":
            entry_constructor = PDFileEntry
        else:
            entry_constructor = GenericFileEntry

    # Now we need to use all the metadata to create the entry
    if entry_constructor is None:
        raise ValueError(f"Cluster type {cluster_type} not recognized")

    return entry_constructor(
        data = data,
        start_time = notion_entry.start_time,
        end_time = notion_entry.start_time + notion_entry.duration if notion_entry.duration is not None else None,
        latitude = notion_entry.latitude,
        longitude = notion_entry.longitude,
        group_id = notion_entry.group_id,
        seq_id = notion_entry.seq_id,
        input_handler_id = handler_id,
        entry_uuid_override = notion_entry.rep_uuid
    )


def split_page_blocks(page_blocks: list[NotionBlock], day_start_time_ms: int, day_end_time_ms: int, group_id: str) -> list[NotionEntry]:
    """
    Splits the raw blocks into sections represented by a notion entry
    A single notion entry may be directly converted into a single entry object
    There are two reasons a block may be split
    1. There is a blank paragraph block
    2. The block cluster type changes
    """
    cur_block_cluster = None
    cur_notion_entry_blocks = []
    notion_entries = []
    start_time_override = None
    for i, block in enumerate(page_blocks):
        if block.type == "paragraph" and len(block.paragraph.rich_text) == 0:
            # We have a blank paragraph block. This marks the end of the current entry
            if len(cur_notion_entry_blocks) > 0:
                notion_entries.append(create_notion_entry(cur_notion_entry_blocks, len(notion_entries), group_id, start_time_override))
                cur_notion_entry_blocks = []
                start_time_override = None
                cur_block_cluster = None
            continue
        if block.type == "paragraph" and parse_date_block(block.paragraph.markdown_text) is not None:
            # We have a date block. We consider this the start of a new entry with the start time as the offset from the start of the day
            if len(cur_notion_entry_blocks) > 0:
                notion_entries.append(create_notion_entry(cur_notion_entry_blocks, len(notion_entries), group_id, start_time_override))
                cur_notion_entry_blocks = []
                cur_block_cluster = None
            start_time_day_offset = parse_date_block(block.paragraph.markdown_text)
            if start_time_day_offset is not None:
                start_time_override = day_start_time_ms + start_time_day_offset
            continue
        else:
            block_cluster = get_cluster_idx(block.type)
            if cur_block_cluster is None:
                cur_block_cluster = block_cluster
            elif cur_block_cluster != block_cluster or not clustering_allowed[block_cluster]:
                # We have a new block cluster. This marks the end of the current entry
                new_notion_entry = create_notion_entry(cur_notion_entry_blocks, len(notion_entries), group_id, start_time_override)
                notion_entries.append(new_notion_entry)
                cur_notion_entry_blocks = []
                cur_block_cluster = block_cluster
                start_time_override = new_notion_entry.start_time  # If there is not a gap, we want to keep the same start time. This means text immediately following an image will have the same start time as the image
            cur_notion_entry_blocks.append(block)
    if len(cur_notion_entry_blocks) > 0:
        # This shouldn't actually happen because notion entries are always ended by a blank paragraph block
        # In case that changes, we add this to handle the case
        notion_entries.append(create_notion_entry(cur_notion_entry_blocks, len(notion_entries), group_id, start_time_override))
    return notion_entries

def resolve_monotonicity(notion_entries: list[NotionEntry], day_start_ms: int, day_end_ms: int) -> list[NotionEntry]:
    """
    Notion entries must be monotonically increasing in time. If they are not, we resolve this by following the rules:
    1. If the entry falls outside of the day range, we set the start_time to the start_time of the previous entry
    2. If an entry decreases in time, but is within the day range, we iterate backwards to find the previous entry
        with a lower timestamp and set all entries between the two to the start time of the previous entry
    """
    cur_time = -1
    for i, entry in enumerate(notion_entries):
        if entry.start_time < day_start_ms or entry.start_time > day_end_ms:
            logger.warning(f"Entry {i} (time: {entry.start_time}) falls outside of the day range ({day_start_ms} - {day_end_ms}). Setting start time to {cur_time}")
            entry.start_time = cur_time
        elif entry.start_time < cur_time:
            # Iterate backwards to find the previous entry with a lower timestamp
            cur_entry = i - 1
            while cur_entry >= 0 and notion_entries[cur_entry].start_time > entry.start_time:
                cur_entry -= 1
            cur_time = notion_entries[cur_entry].start_time
            for j in range(cur_entry + 1, i):
                notion_entries[j].start_time = cur_time
        else:
            cur_time = entry.start_time
    return notion_entries

def block_group_to_entry(block_group: list[NotionBlock]) -> Entry:
    """
    Converts a list of rich text items to an entry
    """
    text = "".join([item.text.content for item in block_group])
    return Entry(data=text)
