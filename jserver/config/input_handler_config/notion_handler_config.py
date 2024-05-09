from pydantic import Field

from .input_handler_config import InputHandlerConfig

from typing import Literal

class NotionHandlerConfig(InputHandlerConfig):
    handler_type: Literal["notion"] = "notion"
    auth_token: str = Field(..., description="The Notion API token")
    auto_generate_today_page: bool = Field(True, description="Whether to automatically generate a new page for today if it doesn't exist")
    testing: bool = Field(False, description="Whether to use the testing page instead of the actual pages")
    recheck_interval: int = Field(90, description="An interval in seconds to recheck an updated page for new changes")
