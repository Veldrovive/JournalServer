"""
Creates a router at /output that serves entries
"""

import json
import tempfile
import shutil
import os
import time

from fastapi import APIRouter, File, UploadFile, Form, Query
from fastapi.responses import JSONResponse

from jserver.storage import ResourceManager
from jserver.entries.output import OutputEntry, entry_to_output
from jserver.storage.primitives import OutputFilter, LocationFilter

from jserver.utils.logger import setup_logging
logger = setup_logging(__name__)

router = APIRouter()

@router.get("/entries", response_model=list[OutputEntry])
async def root(
    start_time: int = Query(None),
    end_time: int | None = Query(None),
    type_whitelist: list[str] | None = Query(None),
    input_handler_ids: list[str] | None = Query(None),
    group_ids: list[str] | None = Query(None),

    min_lat: float | None = Query(None),
    max_lat: float | None = Query(None),
    min_lng: float | None = Query(None),
    max_lng: float | None = Query(None),
):
    rmanager = ResourceManager()  # Get a reference to the singleton instance

    location_filter = None
    if min_lat is not None and max_lat is not None and min_lng is not None and max_lng is not None:
        location_filter = LocationFilter(
            min_lat=min_lat,
            max_lat=max_lat,
            min_lng=min_lng,
            max_lng=max_lng,
        )

    filter = OutputFilter(
        timestamp_after=start_time,
        timestamp_before=end_time,
        entry_types=type_whitelist,
        input_handler_ids=input_handler_ids,
        group_ids=group_ids,
        location=location_filter,
    )

    entry_uuids = rmanager.search_entries(filter)
    entries = rmanager.pull_entries(entry_uuids)
    start_time = time.time()
    output_entries = [entry_to_output(entry) for entry in entries]
    output_data = [entry.model_dump() for entry in output_entries]
    logger.info(f"Time to dump entries: {time.time() - start_time}")

    return JSONResponse(status_code=200, content=output_data)
