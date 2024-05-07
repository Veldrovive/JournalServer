from pydantic import BaseModel, Field

class Caption(BaseModel):
    """
    A caption can either be a markdown string or a reference to another entry
    """
    content: str | None = Field(None, description="The markdown caption of the image")
    entry_uuid: str | None = Field(None, description="The entry UUID of the caption of the image")

class Metadata(BaseModel):
    caption: Caption | None
