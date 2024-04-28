from pydantic import BaseModel, Field
from typing import Any, Generic, TypeVar, Optional, List, TypedDict
from enum import Enum

class Status(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    FAIL = "fail"

ResponseType = TypeVar("ResponseType", bound=BaseModel)
class Response(BaseModel, Generic[ResponseType]):
    status: Status = Field(..., description="Status of the response")
    error: str | None = Field(None, description="Error message")
    data: ResponseType | None = Field(None, description="Response data")

class SensorInfo(BaseModel):
    timestamp: int = Field(..., description="Unix timestamp")
    sensor: str = Field(..., description="Sensor id")
    value: dict[str, Any] = Field(..., description="Sensor value")

class SensorInfoMetadata(BaseModel):
    last_updated: int = Field(..., description="Unix timestamp of last update")

class ReturnedSensorInfo(BaseModel):
    source_uuids: list[str] = Field(..., description="List of source UUIDs")
    metadatas: dict[str, SensorInfoMetadata] = Field(..., description="Metadata for each source UUID")

