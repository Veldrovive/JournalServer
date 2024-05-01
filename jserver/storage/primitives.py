from pydantic import BaseModel, Field

class LocationFilter(BaseModel):
    min_lat: float = Field(..., description="The minimum latitude of the location filter.")
    max_lat: float = Field(..., description="The maximum latitude of the location filter.")
    min_lng: float = Field(..., description="The minimum longitude of the location filter.")
    max_lng: float = Field(..., description="The maximum longitude of the location filter.")

class OutputFilter(BaseModel):
    """
    Defines the types of filter that can be applied to search for entries
    """
    timestamp_after: int | None = Field(None, description="The timestamp after which entries should be returned.")
    timestamp_before: int | None = Field(None, description="The timestamp before which entries should be returned.")
    location: LocationFilter | None = Field(None, description="The location filter to apply to the entries.")
    entry_types: list[str] | None = Field(None, description="The entry types to return.")
    input_handler_ids: list[str] | None = Field(None, description="The input source ids to return.")
    group_ids: list[str] | None = Field(None, description="The source uuids to return.")
