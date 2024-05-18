from pydantic import Field, field_validator, field_serializer

from .input_handler_config import InputHandlerConfig

from typing import Literal

class EvernoteAPIHandlerConfig(InputHandlerConfig):
    handler_type: Literal["evernote"] = "evernote"

    consumer_key: str = Field(..., title="Consumer Key", description="The consumer key for the Evernote API")
    consumer_secret: str = Field(..., title="Consumer Secret", description="The consumer secret for the Evernote API", exclude=True)  # Don't include the consumer secret in the config when sent to the client
