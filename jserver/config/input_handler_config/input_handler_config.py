from pydantic import BaseModel, Field

from typing import Literal

class InputHandlerConfig(BaseModel):
    handler_type: str
    handler_uuid: str = Field(..., description="An internal UUID for the handler")
    handler_name: str = Field(..., description="A human readable name for the handler")
    trigger_check_interval: float | None = Field(None, description="The interval in seconds to check if a trigger has been activated")

class TestInputHandlerConfig(InputHandlerConfig):
    handler_type: Literal["test"] = "test"
    test_file_folder: str = Field(..., description="The folder where test files are stored")
