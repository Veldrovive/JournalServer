"""
Handles the conversion of entry objects to output formats
"""

from pydantic import BaseModel, Field
from .primitives import EntryPrivacy, EntryType, EntryUUID, EntryHash

from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    from jserver.entries import Entry

class OutputEntry(BaseModel):
    """
    An entry that is directly returned to the client
    """
    entry_type: EntryType = Field(..., description="Used as an identifier for what type of entry this is")
    data: Any = Field(..., description="Data specific to the entry type. For example, a text entry would have a string here")
    privacy: EntryPrivacy = Field(EntryPrivacy.PUBLIC, description="Used to determine if the entry should be returned in a query")
    start_time: int = Field(..., description="The start time of the entry in milliseconds since the epoch")
    end_time: int | None = Field(None, description="The end time of the entry in milliseconds since the epoch")
    latitude: float | None = Field(None, description="The latitude of the entry")
    longitude: float | None = Field(None, description="The longitude of the entry")
    height: float | None = Field(None, description="The height of the entry")
    group_id: str | None = Field(None, description="Used to group entries together")
    seq_id: int | None = Field(None, description="Defines where in a group the entry should be placed. Should be unique within a group")
    input_handler_id: str = Field(..., description="The input handler UUID that added the entry")
    tags: list[str] = Field([], description="The tags associated with the entry")

    entry_uuid: EntryUUID = Field(..., description="The UUID of the entry")
    entry_hash: EntryHash = Field(..., description="The hash of the entry")

    @classmethod
    def from_entry(cls, entry: 'Entry') -> "OutputEntry":
        """
        Convert an entry to an output entry
        """
        output_data = entry.construct_output_data()
        dumped_entry = entry.model_dump(exclude={"data"})
        dumped_entry["data"] = output_data
        return cls(**dumped_entry)

def entry_to_output(entry: 'Entry') -> OutputEntry:
    """
    Converts an entry to an output dictionary
    """
    output_entry = OutputEntry.from_entry(entry)
    return output_entry
