"""
A collection of functions for hashing data

All are sha256 hashes and should be reproducible
"""

import hashlib

from jserver.storage import ResourceManager

def hash_text(text: str):
    """
    Hashes a string using the SHA-256 algorithm
    """
    return hashlib.sha256(text.encode()).hexdigest()

def hash_bytes(data: bytes):
    """
    Hashes bytes using the SHA-256 algorithm
    """
    return hashlib.sha256(data).hexdigest()

def hash_stored_file(file_id: str):
    """
    Gets a hash for a file already in the file store
    """
    rmanager = ResourceManager()  # Get the singleton instance of the resource manager
    with rmanager.get_temp_local_file(file_id) as temp_file:
        with open(temp_file, "rb") as f:
            # Read the first 1MB of the file and hash it
            return hash_bytes(f.read(1024 * 1024))
