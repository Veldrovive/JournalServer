from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime

class Pagination(BaseModel):
    afterDate: str = Field(description="The date to use for the pagination. Format: yyyy-MM-dd")
    limit: int = Field(description="The maximum number of items to return in the response.")
    next: str = Field(description="The next pagination URL.")
    offset: int = Field(description="The offset number of the pagination.")
    previous: str = Field(description="The previous pagination URL.")
    sort: str = Field(description="The sort order of entries returned. Default: desc, Allowed: asc | desc")

class ActivityLevelName(str, Enum):
    SEDENTARY = "sedentary"
    LIGHTLY = "lightly"
    FAIRLY = "fairly"
    VERY = "very"

class ActivityLevel(BaseModel):
    name: ActivityLevelName
    minutes: int

class Activity(BaseModel):
    activeDuration: int = Field(description="The duration of the activity in milliseconds")
    activityLevel: list[ActivityLevel] = Field(description="The activity levels for the activity")
    activityName: str = Field(description="Name of the recorded exercise.")
    activityTypeId: int = Field(description="The activityName's identifier number.")
    averageHeartRate: int | None = Field(None, description="The average heart rate during the exercise.")
    calories: int = Field(description="Number of calories burned during the exercise.")
    distance: float | None = Field(None, description="Distance traveled during the exercise.")
    distanceUnit: str | None = Field(None, description="Distance units defined by the Accept-Language header.")
    elevationGain: float | None = Field(None, description="Elevation gained during the exercise.")
    logId: int = Field(description="The activity log identifier for the exercise.")
    logType: str = Field(description="The type of activity log created. Supported: auto_detected | manual | mobile_run | tracker | the name of the 3rd party application")
    originalDuration: int = Field(description="The initial length in time (milliseconds) that the exercise was recorded. This value will contain pauses during the exercise.")
    originalStartTime: str = Field(description="The initial start datetime that the exercise was recorded.")
    steps: int | None = Field(None, description="Number of steps taken during the exercise.")
    tcxLink: str = Field(description="URL to download the TCX file.")

class TCXTrackPointLocal(BaseModel):
    time: datetime = Field(description="The time of the track point.")
    distance: float | None = Field(None, description="The distance of the track point.")
    elevation: float | None = Field(None, description="The elevation of the track point.")
    latitude: float | None = Field(None, description="The latitude of the track point.")
    longitude: float | None = Field(None, description="The longitude of the track point.")
    hr_value: int | None = Field(None, description="The heart rate value of the track point.")
    cadence: int | None = Field(None, description="The cadence of the track point.")

class TCXActivity(BaseModel):
    """
    A class for storing the TCX file details for an activity
    """
    activity_type: str = Field(description="The type of activity")
    altitude_avg: float | None = Field(None, description="The average altitude")
    altitude_max: float | None = Field(None, description="The maximum altitude")
    altitude_min: float | None = Field(None, description="The minimum altitude")
    ascent: float | None = Field(None, description="The ascent")
    avg_speed: float | None = Field(None, description="The average speed")
    calories: int | None = Field(None, description="The calories")
    descent: float | None = Field(None, description="The descent")
    distance: float | None = Field(None, description="The distance")
    duration: float | None = Field(None, description="The duration")
    end_time: datetime | None = Field(None, description="The end time")
    hr_avg: float | None = Field(None, description="The average heart rate")
    hr_max: int | None = Field(None, description="The maximum heart rate")
    hr_min: int | None = Field(None, description="The minimum heart rate")
    max_speed: float | None = Field(None, description="The maximum speed")
    start_time: datetime | None = Field(None, description="The start time")
    trackpoints: list[TCXTrackPointLocal] | None = Field(None, description="The track points")

class DetailedActivity(BaseModel):
    activity: Activity = Field(description="The activity")
    activityTCXData: TCXActivity = Field(description="The TCX data for the activity")
