from pydantic import Field

from .input_handler_config import InputHandlerConfig

from typing import Literal

class NotionHandlerConfig(InputHandlerConfig):
    handler_type: Literal["notion"] = "notion"
    auth_token: str = Field(..., description="The Notion API token")
