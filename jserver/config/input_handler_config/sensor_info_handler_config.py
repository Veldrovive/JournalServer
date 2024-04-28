from pydantic import Field

from .input_handler_config import InputHandlerConfig

from typing import Literal

class SensorInfoHandlerConfig(InputHandlerConfig):
    handler_type: Literal["sensor_info"] = "sensor_info"

    data_source_id: str = Field(..., description="The type of sensor data to be parsed")
    sensor_info_server: str = Field(..., description="The URL of the sensor info server")
