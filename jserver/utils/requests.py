"""
A utility for making http requests
"""

import requests
from typing import Any

from jserver.utils.logger import setup_logging

logger = setup_logging(__name__)

def get_json(url: str) -> Any:
    """
    Makes a GET request to the given url and returns the response as a json dict
    """
    response = requests.get(url)
    # assert response.status_code == 200, f"GET request to {url} failed with status code {response.status_code}"
    if response.status_code != 200:
        logger.error(f"GET request to {url} failed with status code {response.status_code}")
        return None
    return response.json()
