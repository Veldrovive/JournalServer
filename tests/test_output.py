import pytest
import requests

from jserver.storage import ResourceManager
from jserver.entries import entry_to_output
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

def test_output_entry(rmanager: ResourceManager, session_test_generic_file_entry):
    output_entry = entry_to_output(session_test_generic_file_entry)
    logger.debug(f"Output entry: {output_entry}")

    file_url = output_entry.data["file_url"]
    response = requests.get(file_url)
    assert response.status_code == 200
    assert response.text == "Hello World!"

def test_delete_entry(rmanager: ResourceManager, session_test_generic_file_entry):
    rmanager.delete_entry(session_test_generic_file_entry.entry_uuid)
    logger.debug("Deleted entry from database")
