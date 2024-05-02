from pydantic import Field, field_validator, field_serializer
from datetime import datetime

from .input_handler_config import InputHandlerConfig

from typing import Literal

class FitbitAPIHandlerConfig(InputHandlerConfig):
    handler_type: Literal["fitbit_api"] = "fitbit_api"

    client_id: str = Field(..., title="Client ID", description="The client ID for the Fitbit API")
    client_secret: str = Field(..., title="Client Secret", description="The client secret for the Fitbit API", exclude=True)  # Don't include the client secret in the config when sent to the client
    geolocation_downsample_period_s: int = Field(30, title="Geolocation Downsample Period (s)", description="The period in seconds to downsample geolocation data")
    start_date: datetime | None = Field(None, title="Start Date", description="The start date for the Fitbit API data")

    @field_validator("start_date", mode="before")
    def parse_start_date(cls, v):
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        return datetime.fromisoformat(v)

    @field_serializer("start_date")
    def serialize_start_date(self, start_date: datetime | None, _info):
        if start_date is None:
            return None
        return start_date.isoformat()
