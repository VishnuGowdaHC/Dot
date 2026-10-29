"""
Defines persistent storage paths for transcripts, summaries, and databases.
"""

import os

# Base storage directories.
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
STORAGE_DIR = os.path.join(_CURRENT_DIR, "storage")
TRANSCRIPTS_DIR = os.path.join(STORAGE_DIR, "transcripts")
SUMMARIES_DIR = os.path.join(STORAGE_DIR, "summaries")

# Ensure required storage directories exist.
os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)
os.makedirs(SUMMARIES_DIR, exist_ok=True)

