"""
Defines persistent storage paths for transcripts, summaries, and databases.
"""

from dot.config.paths import STORAGE_DIR as _STORAGE_DIR
from dot.config.paths import TRANSCRIPTS_DIR as _TRANSCRIPTS_DIR
from dot.config.paths import SUMMARIES_DIR as _SUMMARIES_DIR

# Base storage directories exported as strings.
STORAGE_DIR = str(_STORAGE_DIR)
TRANSCRIPTS_DIR = str(_TRANSCRIPTS_DIR)
SUMMARIES_DIR = str(_SUMMARIES_DIR)
