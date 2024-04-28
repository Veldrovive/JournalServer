from pydantic import Field

from .input_handler_config import InputHandlerConfig

from typing import Literal

class DayOneHandlerConfig(InputHandlerConfig):
    handler_type: Literal["day_one"] = "day_one"
