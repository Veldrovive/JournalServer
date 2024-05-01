from enum import Enum

class EntryType(str, Enum):
    TEXT = "text"
    GENERIC_FILE = "generic_file"
    TEXT_FILE = "text_file"
    IMAGE_FILE = "image_file"
    VIDEO_FILE = "video_file"
    AUDIO_FILE = "audio_file"
    PDF_FILE = "pdf_file"
    GEOLOCATION = "geolocation"
    ACCELEROMETER = "accelerometer"
    HEART_RATE = "heart_rate"
    SLEEP_STATE = "sleep_state"
    FITBIT_ACTIVITY = "fitbit_activity"

class EntryPrivacy(int, Enum):
    PUBLIC = 0
    SENSITIVE = 1
    PRIVATE = 2

EntryUUID = str
EntryHash = str
