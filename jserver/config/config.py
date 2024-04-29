from pydantic import BaseModel, Field

from jserver.config.input_handler_config import AllInputHandlerConfig

from typing import Literal

############# Database Manager Config #############
class MongoDatabaseManagerConfig(BaseModel):
    manager_type: Literal["mongo"] = "mongo"
    host: str
    port: int
    username: str
    password: str
    database: str

class PostgresDatabaseManagerConfig(BaseModel):
    manager_type: Literal["postgres"] = "postgres"
    host: str
    port: int
    username: str
    password: str
    database: str

DatabaseManagerConfig = MongoDatabaseManagerConfig | PostgresDatabaseManagerConfig
###################################################

############# File Store Config #############
class MinioFileStorageManagerConfig(BaseModel):
    manager_type: Literal["minio"] = "minio"
    host: str
    port: int
    username: str
    password: str
    bucket: str

class S3FileStorageManagerConfig(BaseModel):
    manager_type: Literal["s3"] = "s3"
    host: str
    port: int
    username: str
    password: str
    bucket: str

FileStorageManagerConfig = MinioFileStorageManagerConfig | S3FileStorageManagerConfig
###################################################


class StorageManagerConfig(BaseModel):
    database_manager: DatabaseManagerConfig
    file_storage_manager: FileStorageManagerConfig

class InputConfig(BaseModel):
    input_dir: str
    input_handlers: list[AllInputHandlerConfig]

class OutputConfig(BaseModel):
    port: int
    host: str
    cors: list[str] | None = None

class Config(BaseModel):
    storage_manager: StorageManagerConfig
    input_config: InputConfig
    output_config: OutputConfig
    dev: bool = False
