"""
Creates a router at /input_handlers that receives commands from the client

GET /input_handlers - Returns a list of all input handlers and their configurations

POST /input_handlers/{handler_id}/request_trigger - Takes an optional file and optional metadata form data
    Tells the singleton InputHandlerManager to trigger the handler with the given handler_id
"""
import json
import tempfile
import shutil
import os

from fastapi import APIRouter, File, UploadFile, Form
from fastapi.responses import JSONResponse

from jserver.input_handlers import InputHandlerManager
from jserver.exceptions import *

from jserver.utils.logger import setup_logging
logger = setup_logging(__name__)

router = APIRouter()

@router.get("/")
async def get_input_handlers():
    """
    Returns a list of all input handlers and their configurations
    """
    imanager = InputHandlerManager()  # Get a reference to the singleton instance
    return JSONResponse(status_code=200, content=imanager.get_handler_info())

@router.get("/{handler_id}/")
async def get_input_handler(handler_id: str):
    """
    Returns the configuration of the input handler with the given handler_id
    """
    imanager = InputHandlerManager()
    handler_info = imanager.get_handler_info()

    logger.info(f"Handler info: {handler_info}")
    if handler_id in handler_info:
        return JSONResponse(status_code=200, content=handler_info[handler_id])
    else:
        return JSONResponse(status_code=404, content={"error": f"Handler with id {handler_id} not found"})

@router.post("/{handler_id}/request_trigger")
async def request_trigger(handler_id: str, file: UploadFile = File(None), metadata: str = Form(None)):
    """
    Takes an optional file and optional metadata form data
    Tells the singleton InputHandlerManager to trigger the handler with the given handler_id
    """
    imanager = InputHandlerManager()

    tempdir = None
    if file is None:
        local_file = None
    else:
        file_name = file.filename
        tempdir = tempfile.mkdtemp()
        local_file = os.path.join(tempdir, file_name)
        with open(local_file, "wb") as f:
            shutil.copyfileobj(file.file, f)

    if metadata is None:
        parsed_metadata = None
    else:
        try:
            parsed_metadata = json.loads(metadata)
        except json.JSONDecodeError as e:
            return JSONResponse(status_code=400, content={"error": f"Failed to parse metadata: {str(e)}"})

    logger.info(f"Received trigger request for handler {handler_id} with file {local_file} and metadata {parsed_metadata}")

    success = True
    error = None
    entry_insertion_log = None
    try:
        entry_insertion_log = await imanager.on_trigger_request(handler_id, local_file, parsed_metadata)
    except Exception as e:
        logger.error(f"Failed to trigger handler {handler_id}: {e}")
        success = False
        error = str(e)
    finally:
        if tempdir is not None:
            shutil.rmtree(tempdir)

    status_code = 200 if success else 500
    content = {"success": success}
    if error is not None:
        content["error"] = error
    if entry_insertion_log is not None:
        content["entry_insertion_log"] = [entry.model_dump(exclude={'entry'}) for entry in entry_insertion_log]

    return JSONResponse(status_code=status_code, content=content)

@router.post("/{handler_id}/rpc/{rpc_name}")
async def rpc_handler(handler_id: str, rpc_name: str, body: dict):
    """
    Takes an RPC request and sends it to the handler with the given handler_id
    """
    imanager = InputHandlerManager()
    try:
        res = imanager.handle_rpc_request(handler_id, rpc_name, body)
        return JSONResponse(status_code=200, content=res)
    except InputHandlerNotFoundException:
        return JSONResponse(status_code=404, content={"error": f"Handler with id {handler_id} not found"})
    except RPCNameNotFoundException:
        return JSONResponse(status_code=404, content={"error": f"RPC with name {rpc_name} not found"})
