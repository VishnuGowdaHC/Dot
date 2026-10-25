"""
Shared ChromaDB client module.
Provides a singleton instance of the persistent ChromaDB client.
"""

import os
import chromadb
from typing import Optional

# Path to the persistent ChromaDB storage directory
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_STORAGE_PATH = os.path.join(_CURRENT_DIR, "storage", "chroma_db")

# Module-level singleton instance
_CHROMA_CLIENT: Optional[chromadb.PersistentClient] = None


def get_chroma_client() -> chromadb.PersistentClient:
    """Returns the shared ChromaDB PersistentClient singleton instance.
    
    Initializes the database connection on the first call.
    Subsequent calls return the cached in-memory instance.
    """
    global _CHROMA_CLIENT
    if _CHROMA_CLIENT is None:
        os.makedirs(_STORAGE_PATH, exist_ok=True)
        _CHROMA_CLIENT = chromadb.PersistentClient(path=_STORAGE_PATH)
    return _CHROMA_CLIENT


def get_collection(name: str):
    """Retrieves or creates a ChromaDB collection with the specified name."""
    client = get_chroma_client()
    return client.get_or_create_collection(name=name)
