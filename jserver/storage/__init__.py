from .resource_manager import ResourceManager
# from .entry_manager import EntryManager
from jserver.storage.file.s3_file_manager import S3FileManager
from jserver.storage.db.mongo_database_manager import MongoDatabaseManager

def construct_db(config: 'Config'):
    """
    Constructs the singleton instance of the ResourceManager class
    """
    database_config = config.storage_manager.database_manager
    if database_config.manager_type == "mongo":
        return MongoDatabaseManager(config)
    elif database_config.manager_type == "postgres":
        raise NotImplementedError("Postgres is not yet supported")
    else:
        raise ValueError(f"Unknown database manager type: {database_config.manager_type}")

def construct_file_store(config: 'Config'):
    """
    Constructs the singleton instance of the ResourceManager class
    """
    file_storage_config = config.storage_manager.file_storage_manager
    if file_storage_config.manager_type == "minio":
        return S3FileManager(config)
    elif file_storage_config.manager_type == "s3":
        return S3FileManager(config)
    else:
        raise ValueError(f"Unknown file storage manager type: {file_storage_config.manager_type}")

def construct_manager(config: 'Config'):
    """
    Constructs the singleton instance of the ResourceManager class
    """
    db = construct_db(config)
    file_store = construct_file_store(config)
    return ResourceManager.construct_manager(db, file_store)
