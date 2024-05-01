from pydantic import BaseModel, Discriminator, Field

from jserver.entries.types.generic_entries import TextEntry, GenericFileEntry
from jserver.entries.types.file_entries import TextFileEntry, ImageFileEntry, VideoFileEntry, AudioFileEntry, PDFileEntry
from jserver.entries.types.personal_sensor_entries import GeolocationEntry, HeartRateEntry, SleepStateEntry, AccelerometerEntry
from jserver.entries.types.fitbit_api import FitbitActivityEntry

from jserver.entries.output import entry_to_output

Entry = TextEntry | GenericFileEntry | TextFileEntry | ImageFileEntry | \
    VideoFileEntry | AudioFileEntry | PDFileEntry | GeolocationEntry | \
    HeartRateEntry | SleepStateEntry | AccelerometerEntry | FitbitActivityEntry

class EntryValidator(BaseModel):
    entry: Entry = Field(..., description="The entry to validate", discriminator="entry_type")

def validate_entry(entry_data):
    validated_entry = EntryValidator.model_validate({ "entry": entry_data })
    return validated_entry.entry
