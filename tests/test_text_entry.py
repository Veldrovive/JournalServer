import pytest

from jserver.entries import validate_entry
from jserver.entries import TextEntry
from jserver.storage import ResourceManager
from jserver.exceptions import *

from jserver.utils.logger import setup_logging
logger = setup_logging(__name__)

def test_insert_entry(rmanager: ResourceManager, session_test_text_entry: TextEntry):
    logger.debug(f"Constructed entry: {session_test_text_entry}")
    rmanager.insert_entry(session_test_text_entry)
    logger.debug("Inserted entry into database")

    # Now if we try to insert the same entry we should get an exception
    with pytest.raises(EntryAlreadyExistsException):
        rmanager.insert_entry(session_test_text_entry)

def test_recall_entry(rmanager: ResourceManager, session_test_text_entry: TextEntry):
    logger.debug(f"Recalling entry: {session_test_text_entry}")
    entry = rmanager.pull_entry(session_test_text_entry.entry_uuid)
    logger.debug(f"Recalled entry: {entry}")
    assert entry == session_test_text_entry

def test_delete_entry(rmanager: ResourceManager, session_test_text_entry: TextEntry):
    logger.debug(f"Deleting entry: {session_test_text_entry}")
    rmanager.delete_entry(session_test_text_entry.entry_uuid)
    logger.debug("Deleted entry from database")

    # Now if we search for it we should get an exception
    with pytest.raises(EntryNotFoundException):
        rmanager.pull_entry(session_test_text_entry.entry_uuid)
