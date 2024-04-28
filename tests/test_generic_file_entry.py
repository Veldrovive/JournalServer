import pytest

from jserver.storage import ResourceManager
from jserver.exceptions import *

from jserver.utils.logger import setup_logging
logger = setup_logging(__name__)

def test_insert_entry(rmanager: ResourceManager, session_test_generic_file_entry):
    logger.debug(f"Constructed entry: {session_test_generic_file_entry}")
    rmanager.insert_entry(session_test_generic_file_entry)
    logger.debug("Inserted entry into database")

    # Now if we try to insert the same entry we should get an exception
    with pytest.raises(EntryAlreadyExistsException):
        rmanager.insert_entry(session_test_generic_file_entry)

def test_recall_entry(rmanager: ResourceManager, session_test_generic_file_entry):
    logger.debug(f"Recalling entry: {session_test_generic_file_entry}")
    entry = rmanager.pull_entry(session_test_generic_file_entry.entry_uuid)
    logger.debug(f"Recalled entry: {entry}")
    assert entry == session_test_generic_file_entry

    # We can also read the file and see if it matches
    with rmanager.get_temp_local_file(entry.data.file_id) as temp_file:
        with open(temp_file, "r") as f:
            file_contents = f.read()
            assert file_contents == "Hello World!"

def test_delete_entry(rmanager: ResourceManager, session_test_generic_file_entry):
    logger.debug(f"Deleting entry: {session_test_generic_file_entry}")
    rmanager.delete_entry(session_test_generic_file_entry.entry_uuid)
    logger.debug("Deleted entry from database")

    # Now if we search for it we should get an exception
    with pytest.raises(EntryNotFoundException):
        rmanager.pull_entry(session_test_generic_file_entry.entry_uuid)
