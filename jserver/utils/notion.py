import datetime
from contextlib import contextmanager
import tempfile
import pathlib
import urllib
import requests
import os

from pydantic import BaseModel, Field, ValidationError, computed_field
from notion_client import Client
from notion_client.helpers import iterate_paginated_api as paginate

from jserver.entries import Entry

from typing import Literal, Any, ClassVar

class RichTextLink(BaseModel):
    url: str = Field(..., description="The url of the link")

class RichTextText(BaseModel):
    content: str = Field(..., description="The content of the text")
    link: RichTextLink | None = Field(None, description="The link of the text")

class RichTextAnnotations(BaseModel):
    bold: bool
    italic: bool
    strikethrough: bool
    underline: bool
    code: bool
    color: str | None = None

class RichTextItem(BaseModel):
    type: Literal["text"] = "text"
    text: RichTextText
    annotations: RichTextAnnotations
    plain_text: str
    href: str | None = None

    def to_markdown(self) -> str:
        """
        Converts the rich text item to markdown
        """
        markdown = self.plain_text
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
        return markdown

class NotionPage(BaseModel):
    id: str = Field(..., description="The id of the page")
    last_edited_time: str = Field(..., description="The last edited time of the page. ISO format 2024-05-05T21:55:00.000Z")
    parent_page_id: str | None = Field(None, description="The id of the parent page. None if the parent is not a page")
    plaintext_title: str = Field(..., description="The plaintext title of the page")
    url: str = Field(..., description="The url of the page")

    @property
    @computed_field
    def last_edit_time_ms(self) -> int:
        """
        Returns the last edit time in milliseconds
        """
        return int(datetime.datetime.fromisoformat(self.last_edited_time).timestamp() * 1000)

class NotionBlock(BaseModel):
    object: Literal["block"] = "block"
    id: str = Field(..., description="The id of the block")
    created_time: str = Field(..., description="The created time of the block. ISO format 2024-05-05T21:55:00.000Z")
    last_edited_time: str = Field(..., description="The last edited time of the block. ISO format 2024-05-05T21:55:00.000Z")
    type: str = Field(..., description="The type of the block")

    @property
    @computed_field
    def last_edit_time_ms(self) -> int:
        """
        Returns the last edit time in milliseconds
        """
        return int(datetime.datetime.fromisoformat(self.last_edited_time).timestamp() * 1000)

    @property
    @computed_field
    def created_time_ms(self) -> int:
        """
        Returns the created time in milliseconds
        """
        return int(datetime.datetime.fromisoformat(self.created_time).timestamp() * 1000)


######### Notion Block Type Definitions #########
class NotionRichTextData(BaseModel):
    rich_text: list[RichTextItem] = Field([], description="The rich text of the bulleted list", exclude=True)
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

class NotionHeadingOneBlock(NotionBlock):
    _type: ClassVar[str] = "heading_1"
    type: Literal["heading_1"] = "heading_1"
    heading_1: NotionRichTextData = Field(..., description="The heading 1 data of the block")

class NotionHeadingTwoBlock(NotionBlock):
    _type: ClassVar[str] = "heading_2"
    type: Literal["heading_2"] = "heading_2"
    heading_2: NotionRichTextData = Field(..., description="The heading 2 data of the block")

class NotionHeadingThreeBlock(NotionBlock):
    _type: ClassVar[str] = "heading_3"
    type: Literal["heading_3"] = "heading_3"
    heading_3: NotionRichTextData = Field(..., description="The heading 3 data of the block")

class NotionBulletedListBlock(NotionBlock):
    _type: ClassVar[str] = "bulleted_list_item"
    type: Literal["bulleted_list_item"] = "bulleted_list_item"
    bulleted_list_item: NotionRichTextData = Field(..., description="The bulleted list data of the block")

class NotionNumberedListBlock(NotionBlock):
    _type: ClassVar[str] = "numbered_list_item"
    type: Literal["numbered_list_item"] = "numbered_list_item"
    numbered_list_item: NotionRichTextData = Field(..., description="The numbered list data of the block")

class NotionQuoteBlock(NotionBlock):
    _type: ClassVar[str] = "quote"
    type: Literal["quote"] = "quote"
    quote: NotionRichTextData = Field(..., description="The quote data of the block")

class NotionFileData(BaseModel):
    caption: list[RichTextItem] = Field([], description="The caption of the image", exclude=True)
    type: str = Field(..., description="file or external")
    external: dict[str, str] | None = Field(None, description="The external data of the image. None if the image is a file. Contains only `url` key.")
    file: dict[str, str] | None = Field(None, description="The file data of the image. None if the image is external. Contains `url` and `expiry_time` keys.")
    name: str | None = Field(None, description="The name of the file")

    @computed_field
    @property
    def markdown_caption(self) -> str:
        """
        Converts the caption to markdown
        """
        return "".join([item.to_markdown() for item in self.caption])

    @contextmanager
    def open_file(self) -> dict[str, Any]:
        """
        Download the file and returns a temporary file object along with the file name
        {
            file: tempfile,
            name: str,  ("test.ext")
            type: str (".ext")
        }
        """
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            file_url = self.file["url"] if self.type == "file" else self.external["url"]
            name = None
            if self.name:
                name = self.name
            else:
                # Then we need to get the name based on the url
                name = pathlib.Path(urllib.parse.urlparse(file_url).path).name
            if name:
                ext = pathlib.Path(name).suffix

            response = requests.get(file_url)
            temp_file.write(response.content)
            temp_file.seek(0)

            try:
                yield {
                    "file": temp_file,
                    "name": name,
                    "type": ext
                }
            except Exception as e:
                raise e
            finally:
                os.unlink(temp_file.name)


class NotionImageBlock(NotionBlock):
    _type: ClassVar[str] = "image"
    type: Literal["image"] = "image"
    image: NotionFileData = Field(..., description="The image data of the block")

class NotionVideoBlock(NotionBlock):
    _type: ClassVar[str] = "video"
    type: Literal["video"] = "video"
    video: NotionFileData = Field(..., description="The video data of the block")

class NotionAudioBlock(NotionBlock):
    _type: ClassVar[str] = "audio"
    type: Literal["audio"] = "audio"
    audio: NotionFileData = Field(..., description="The audio data of the block")

class NotionGenericFileBlock(NotionBlock):
    _type: ClassVar[str] = "file"
    type: Literal["file"] = "file"
    file: NotionFileData = Field(..., description="The file data of the block")

class NotionEquationData(BaseModel):
    expression: str = Field(..., description="The latex expression of the equation")

class NotionEquationBlock(NotionBlock):
    _type: ClassVar[str] = "equation"
    type: Literal["equation"] = "equation"
    equation: NotionEquationData = Field(..., description="The equation data of the block")

class NotionCodeData(BaseModel):
    caption: list[RichTextItem] = Field([], description="The caption of the code block", exclude=True)
    rich_text: list[RichTextItem] = Field([], description="The rich text of the code block", exclude=True)
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

# AllNotionBlockTypes = NotionImageBlock | NotionBulletedListBlock | NotionHeadingThreeBlock | NotionHeadingTwoBlock | \
#     NotionHeadingOneBlock | NotionParagraphBlock | NotionVideoBlock | NotionAudioBlock | NotionGenericFileBlock | \
#     NotionEquationBlock | NotionCodeBlock | NotionQuoteBlock

AllNotionBlockTypes = [NotionImageBlock, NotionBulletedListBlock, NotionNumberedListBlock, NotionHeadingThreeBlock, NotionHeadingTwoBlock,
    NotionHeadingOneBlock, NotionParagraphBlock, NotionVideoBlock, NotionAudioBlock, NotionGenericFileBlock,
    NotionEquationBlock, NotionCodeBlock, NotionQuoteBlock]

# class NotionBlockContainer(BaseModel):
#     block: AllNotionBlockTypes = Field(..., description="The block data")
###########################################

class NotionDayPage(NotionPage):
    """
    Stores the information necessary to look up if this is an existing day page in the database

    If the last_edited_time has not changed since the last time the page was processed, then the page is not processed again

    The block Ids are used to check if a block that was previously processed has been removed. In that case the entry should be deleted.
    """
    blocks: list[NotionBlock] = Field([], description="The blocks of the page")

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
                    print(f"Error validating block {i}: {json.dumps(block_json, indent=2)}")
                    raise e
        else:
            raise ValueError(f"Block type {block_json['type']} not recognized")

    return blocks

def day_page_json_to_model(page_json: dict[str, Any]) -> NotionPage:
    """
    Converts a page json to a notion page model
    """
    return NotionDayPage.model_validate(page_json)

def block_group_to_entry(block_group: list[NotionBlock]) -> Entry:
    """
    Converts a list of rich text items to an entry
    """
    text = "".join([item.text.content for item in block_group])
    return Entry(data=text)
