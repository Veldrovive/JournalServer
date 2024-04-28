from pydantic import BaseModel, Field, computed_field, field_validator

from jserver.entries.primitives import *
from jserver.utils import hashers
from jserver.entries.entry import EntryABC
from jserver.storage import ResourceManager

from typing import Any, Literal, ClassVar

class Geolocation(BaseModel):
    accuracy: float | None = Field(None, description="The accuracy of the location in meters.")
    altitude: float | None = Field(None, description="The altitude of the location in meters.")
    altitudeAccuracy: float | None = Field(None, description="The accuracy of the altitude in meters.")
    heading: float | None = Field(None, description="The heading of the location in degrees.")
    latitude: float = Field(..., description="The latitude of the location.")
    longitude: float = Field(..., description="The longitude of the location.")
    speed: float | None = Field(None, description="The speed of the location in meters per second.")

class GeolocationEntry(EntryABC):
    """
    A type of entry that is entirely used to store a location and some metadata
    """
    data: Geolocation = Field(..., description="The geolocation data.")
    entry_type: Literal[EntryType.GEOLOCATION] = EntryType.GEOLOCATION

    @computed_field
    @property
    def entry_uuid(self) -> EntryUUID:
        return f"location-{self.start_time}-{self.entry_hash}"

    @computed_field
    @property
    def entry_hash(self) -> EntryHash:
        return hashers.hash_text(self.data.model_dump_json())

    def construct_output_data(self) -> dict[str, Any]:
        return self.data.model_dump()


class Vec3D(BaseModel):
    x: float
    y: float
    z: float

class AccelerometerData(BaseModel):
    mean: Vec3D = Field(..., description="The mean of the accelerometer data.")
    variance: Vec3D | None = Field(None, description="The variance of the accelerometer data.")
    skewness: Vec3D | None = Field(None, description="The skewness of the accelerometer data.")
    kurtosis: Vec3D | None = Field(None, description="The kurtosis of the accelerometer data.")

class AccelerometerEntry(EntryABC):
    """
    A type of entry that is entirely used to store a location and some metadata
    """
    data: AccelerometerData = Field(..., description="The accelerometer data.")
    entry_type: Literal[EntryType.ACCELEROMETER] = EntryType.ACCELEROMETER

    @computed_field
    @property
    def entry_uuid(self) -> EntryUUID:
        return f"accelerometer-{self.start_time}-{self.entry_hash}"

    @computed_field
    @property
    def entry_hash(self) -> EntryHash:
        return hashers.hash_text(self.data.model_dump_json())

    def construct_output_data(self) -> dict[str, Any]:
        return self.data.model_dump()


class HeartRate(BaseModel):
    heart_rate: float

class HeartRateEntry(EntryABC):
    """
    A type of entry that is entirely used to store a location and some metadata
    """
    data: HeartRate = Field(..., description="The heart rate data.")
    entry_type: Literal[EntryType.HEART_RATE] = EntryType.HEART_RATE

    @computed_field
    @property
    def entry_uuid(self) -> EntryUUID:
        return f"heart_rate-{self.start_time}-{self.entry_hash}"

    @computed_field
    @property
    def entry_hash(self) -> EntryHash:
        return hashers.hash_text(self.data.model_dump_json())

    def construct_output_data(self) -> dict[str, Any]:
        return self.data.model_dump()


class SleepState(BaseModel):
    state: str

class SleepStateEntry(EntryABC):
    """
    A type of entry that is entirely used to store a location and some metadata
    """
    data: SleepState = Field(..., description="The sleep state data.")
    entry_type: Literal[EntryType.SLEEP_STATE] = EntryType.SLEEP_STATE

    @computed_field
    @property
    def entry_uuid(self) -> EntryUUID:
        return f"sleep_state-{self.start_time}-{self.entry_hash}"

    @computed_field
    @property
    def entry_hash(self) -> EntryHash:
        return hashers.hash_text(self.data.model_dump_json())

    def construct_output_data(self) -> dict[str, Any]:
        return self.data.model_dump()

