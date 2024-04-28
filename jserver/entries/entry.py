"""
Defines the base class for an Entry object as well as associated enums
"""

from abc import ABC, abstractmethod
from pydantic import BaseModel, Field, computed_field

from jserver.entries.primitives import *

from typing import Any

class EntryABC(BaseModel, ABC):
    entry_type: EntryType = Field(..., description="Used as an identifier for what type of entry this is")
    data: Any = Field(..., description="Data specific to the entry type. For example, a text entry would have a string here")
    metadata: Any | None = Field(None, description="Metadata associated with the entry")
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
    mutation_count: int = Field(0, description="The number of times the entry has been mutated")

    @abstractmethod
    @computed_field
    @property
    def entry_uuid(self) -> EntryUUID:
        """
        Generate the entry UUID based on the entry type

        Used to check if an entry already exists in the database
        """
        raise NotImplementedError

    @abstractmethod
    @computed_field
    @property
    def entry_hash(self) -> EntryHash:
        """
        Generate the entry hash based on the data

        Often used in the entry UUID generation
        """
        raise NotImplementedError

    @abstractmethod
    def construct_output_data(self) -> Any:
        """
        Defines how the outside world will see the entry data. For a simple entry like a string this
        will be identity.

        For a type that contains a file, this would convert the file id to a presigned URL.
        """
        raise NotImplementedError
