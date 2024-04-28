"""
Creates entry types for common file types
"""

from .generic_entries import GenericFileEntry
from ..primitives import EntryType

from typing import Literal

class TextFileEntry(GenericFileEntry):
    """
    Represents a text file entry
    """
    entry_type: Literal[EntryType.TEXT_FILE] = EntryType.TEXT_FILE
    valid_extensions = ["txt"]

class ImageFileEntry(GenericFileEntry):
    """
    Represents an image file entry
    """
    entry_type: Literal[EntryType.IMAGE_FILE] = EntryType.IMAGE_FILE
    valid_extensions = ["jpg", "jpeg", "png", "gif", "webp", "bmp", "tiff", "svg", "ico", "heic", "heif", "avif"]

class VideoFileEntry(GenericFileEntry):
    """
    Represents a video file entry
    """
    entry_type: Literal[EntryType.VIDEO_FILE] = EntryType.VIDEO_FILE
    valid_extensions = ["mp4", "avi", "mkv", "mov", "webm", "flv", "wmv", "3gp", "3g2", "m4v", "mpg", "mpeg", "m2v", "m4v", "ts"]

class AudioFileEntry(GenericFileEntry):
    """
    Represents an audio file entry
    """
    entry_type: Literal[EntryType.AUDIO_FILE] = EntryType.AUDIO_FILE
    valid_extensions = ["mp3", "wav", "flac", "ogg", "m4a", "wma", "aac", "aiff", "alac", "dsd", "pcm", "mp2", "mka", "m3u", "m3u8"]

class PDFileEntry(GenericFileEntry):
    """
    Represents a PDF file entry
    """
    entry_type: Literal[EntryType.PDF_FILE] = EntryType.PDF_FILE
    valid_extensions = ["pdf"]
