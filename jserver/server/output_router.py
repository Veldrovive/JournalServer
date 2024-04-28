"""
Creates a router at /output that serves entries
"""

import json
import tempfile
import shutil
import os

from fastapi import APIRouter, File, UploadFile, Form, Query
from fastapi.responses import JSONResponse

from jserver.storage import ResourceManager
from jserver.entries.output import OutputEntry, entry_to_output
from jserver.storage.primitives import OutputFilter

from jserver.utils.logger import setup_logging
logger = setup_logging(__name__)

router = APIRouter()

@router.get("/entries", response_model=list[OutputEntry])
async def root(
    start_time: int = Query(None),
    end_time: int | None = Query(None),
    type_whitelist: list[str] | None = Query(None),
    input_source_ids: list[str] | None = Query(None),
    source_uuids: list[str] | None = Query(None),

    location_lat: float | None = Query(None),
    location_lon: float | None = Query(None),
    location_radius: float | None = Query(None),
):
    rmanager = ResourceManager()  # Get a reference to the singleton instance

    location_filter = None
    if location_lat is not None and location_lon is not None and location_radius is not None:
        location_filter = LocationFilter(
            center=(location_lat, location_lon),
            radius=location_radius,
        )

    filter = OutputFilter(
        timestamp_after=start_time,
        timestamp_before=end_time,
        entry_types=type_whitelist,
        input_source_ids=input_source_ids,
        source_uuids=source_uuids,
        location=location_filter,
    )

    entry_uuids = rmanager.search_entries(filter)
    entries = rmanager.pull_entries(entry_uuids)
    output_entries = [entry_to_output(entry) for entry in entries]
    output_data = [entry.model_dump() for entry in output_entries]

    return JSONResponse(status_code=200, content=output_data)
