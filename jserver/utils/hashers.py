"""
A collection of functions for hashing data

All are sha256 hashes and should be reproducible
"""

import hashlib

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
