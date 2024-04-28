from pydantic import BaseModel, Field

class LocationFilter(BaseModel):
    center: tuple[float, float] = Field(..., description="The center of the location filter in lat lon.")
    radius: float = Field(..., description="The half side length of the square location filter.")

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
