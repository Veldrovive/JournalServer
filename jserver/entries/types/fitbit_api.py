from pydantic import BaseModel, Field, computed_field, field_validator

from jserver.entries.primitives import *
from jserver.utils import hashers
from jserver.entries.entry import EntryABC
from jserver.storage import ResourceManager

from typing import Any, Literal, ClassVar

from jserver.shared_models.fitbit_api import Activity

class FitbitActivityEntry(EntryABC):
    """
    Stores a fitbit activity.
    """
    data: Activity = Field(..., description="The fitbit activity data.")
    entry_type: Literal[EntryType.FITBIT_ACTIVITY] = EntryType.FITBIT_ACTIVITY

    @computed_field
    @property
    def entry_uuid(self) -> EntryUUID:
        return f"fitbit-activity-{self.start_time}-{self.data.logId}"

    @computed_field
    @property
    def entry_hash(self) -> EntryHash:
        return hashers.hash_text(self.data.model_dump_json())

    def construct_output_data(self) -> dict[str, Any]:
        return self.data.model_dump()
