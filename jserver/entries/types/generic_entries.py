from pydantic import BaseModel, Field, computed_field, field_validator
from pathlib import Path

from jserver.entries.primitives import *
from jserver.utils import hashers
from jserver.entries.entry import EntryABC
from jserver.storage import ResourceManager

from typing import Any, Literal, ClassVar

class TextEntry(EntryABC):
    entry_type: Literal[EntryType.TEXT] = EntryType.TEXT
    data: str = Field(..., description="The text data of the entry")

    @computed_field
    @property
    def entry_uuid(self) -> EntryUUID:
        """
        There isn't an optimal way to catch mutations of text entries because they do not have a unique identifier.
        The best we can do is use the text itself as the identifier, but then if the text is changed the entry will be considered new.
        """
        return f"text-{self.input_handler_id}-{self.start_time}-{self.entry_hash}"

    @computed_field
    @property
    def entry_hash(self) -> EntryHash:
        return hashers.hash_text(self.data)

    def construct_output_data(self) -> str:
        return self.data


class FileDetail(BaseModel):
    file_id: str = Field(..., description="The file ID of the file in the file store")
    file_name: str = Field(..., description="The original name of the file")
    file_type: str = Field(..., description="The original extension of the file (e.g. .txt, .png)")
    file_metadata: dict[str, Any] = Field({}, description="Metadata associated with the file")

class GenericFileEntry(EntryABC):
    entry_type: Literal[EntryType.GENERIC_FILE] = EntryType.GENERIC_FILE
    data: FileDetail = Field(..., description="The file data of the entry")

    valid_extensions: ClassVar[list[str] | None] = None # Use any extension

    @classmethod
    def generate_file_detail(cls, file_path: str, file_metadata: dict[str, Any], use_path_as_id=True) -> FileDetail:
        """
        Generates a file detail object from a file path and metadata

        Uses the absolute path as the file id if use_path_as_id is True
        """
        path = Path(file_path)
        assert path.exists(), "File path does not exist"
        assert path.is_file(), "File path is not a file"
        file_name = path.name
        file_extension = path.suffix  # Includes the dot
        assert file_extension[0] == ".", "File extension must start with a dot"

        return FileDetail(
            file_id=str(path.absolute()) if use_path_as_id else None,
            file_name=file_name,
            file_type=file_extension,
            file_metadata=file_metadata
        )

    @classmethod
    def is_valid_extension(cls, ext: str):
        """
        if ext or .ext is a member of valid_extensions
        """
        if cls.valid_extensions is None:
            return True
        if ext.startswith("."):
            ext = ext[1:]
        ext = ext.lower()
        return ext in cls.valid_extensions

    # Ensure that the file type is a valid extension
    @field_validator("data")
    def check_file_type(cls, value):
        ext = value.file_type
        if not cls.is_valid_extension(ext):
            raise ValueError(f"Invalid file extension: {ext}")
        return value

    @computed_field
    @property
    def _entry_uuid(self) -> EntryUUID:
        return f"file-{self.start_time}-{self.entry_hash}"

    @computed_field
    @property
    def _entry_hash(self) -> EntryHash:
        """
        We need to make sure the hash will not change if we try to reupload the same file so we hash the file name, file type and file metadata
        which should be unique when used in conjunction with the timestamp.
        Basically it is highly unlikely that two files with the same name, type and metadata will be uploaded at the same time.
        """
        return hashers.hash_text(self.data.file_name + self.data.file_type + str(self.data.file_metadata))

    def construct_output_data(self):
        """
        Converts the file id to a presigned URL
        """
        rmanager = ResourceManager()
        url = rmanager.get_file_url(self.data.file_id)
        return {
            "file_url": url,
            "file_name": self.data.file_name,
            "file_type": self.data.file_type,
            "file_metadata": self.data.file_metadata
        }
