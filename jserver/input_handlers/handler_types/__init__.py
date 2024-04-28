

from jserver.config import AllInputHandlerConfig
from jserver.config.input_handler_config import *

from .test_input_handler import TestInputHandler
from .day_one_input_handler import DayOneInputHandler
from .sensor_info_input_handler import SensorInfoInputHandler

from typing import Callable

def construct_input_handler(handler_config: AllInputHandlerConfig, on_entries_inserted_cb: Callable):
    """
    Identifies the correct input handler based on the input handler config type and constructs it
    """
    handler_id = handler_config.handler_uuid
    if isinstance(handler_config, TestInputHandlerConfig):
        return TestInputHandler(handler_id, handler_config, on_entries_inserted_cb)
    elif isinstance(handler_config, DayOneHandlerConfig):
        return DayOneInputHandler(handler_id, handler_config, on_entries_inserted_cb)
    elif isinstance(handler_config, SensorInfoHandlerConfig):
        return SensorInfoInputHandler(handler_id, handler_config, on_entries_inserted_cb)
    else:
        raise ValueError(f"Unknown input handler config type: {handler_config}")
